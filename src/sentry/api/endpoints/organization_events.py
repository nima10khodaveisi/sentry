import logging

import sentry_sdk
from rest_framework.exceptions import ParseError
from rest_framework.request import Request
from rest_framework.response import Response

from sentry import features
from sentry.api.bases import NoProjects, OrganizationEventsV2EndpointBase
from sentry.api.paginator import GenericOffsetPaginator
from sentry.api.utils import InvalidParams
from sentry.search.events.fields import is_function
from sentry.snuba import discover, metrics_enhanced_performance

logger = logging.getLogger(__name__)

METRICS_ENHANCED_REFERRERS = {
    "api.performance.landing-table",
}

ALLOWED_EVENTS_REFERRERS = {
    "api.organization-events",
    "api.organization-events-v2",
    "api.dashboards.tablewidget",
    "api.dashboards.bignumberwidget",
    "api.discover.transactions-list",
    "api.discover.query-table",
    "api.performance.vitals-cards",
    "api.performance.landing-table",
    "api.performance.transaction-summary",
    "api.performance.transaction-spans",
    "api.performance.status-breakdown",
    "api.performance.vital-detail",
    "api.performance.durationpercentilechart",
    "api.performance.tag-page",
    "api.trace-view.span-detail",
    "api.trace-view.errors-view",
    "api.trace-view.hover-card",
}

ALLOWED_EVENTS_GEO_REFERRERS = {
    "api.organization-events-geo",
    "api.dashboards.worldmapwidget",
}

API_TOKEN_REFERRER = "api.auth-token.events"


class OrganizationEventsV2Endpoint(OrganizationEventsV2EndpointBase):
    def get(self, request: Request, organization) -> Response:
        if not self.has_feature(organization, request):
            return Response(status=404)

        try:
            params = self.get_snuba_params(request, organization)
        except NoProjects:
            return Response([])
        except InvalidParams as err:
            raise ParseError(err)

        referrer = request.GET.get("referrer")
        use_metrics = features.has(
            "organizations:performance-use-metrics", organization=organization, actor=request.user
        ) or features.has(
            "organizations:dashboards-mep", organization=organization, actor=request.user
        )
        performance_dry_run_mep = features.has(
            "organizations:performance-dry-run-mep", organization=organization, actor=request.user
        )

        # This param will be deprecated in favour of dataset
        if "metricsEnhanced" in request.GET:
            metrics_enhanced = request.GET.get("metricsEnhanced") == "1" and use_metrics
            dataset = discover if not metrics_enhanced else metrics_enhanced_performance
        else:
            dataset = self.get_dataset(request) if use_metrics else discover
            metrics_enhanced = dataset != discover

        sentry_sdk.set_tag("performance.metrics_enhanced", metrics_enhanced)
        allow_metric_aggregates = request.GET.get("preventMetricAggregates") != "1"

        query_modified_by_user = request.GET.get("user_modified")
        if query_modified_by_user in ["true", "false"]:
            sentry_sdk.set_tag("query.user_modified", query_modified_by_user)
        referrer = (
            referrer if referrer in ALLOWED_EVENTS_REFERRERS else "api.organization-events-v2"
        )

        def data_fn(offset, limit):
            query_details = {
                "selected_columns": self.get_field_list(organization, request),
                "query": request.GET.get("query"),
                "params": params,
                "equations": self.get_equation_list(organization, request),
                "orderby": self.get_orderby(request),
                "offset": offset,
                "limit": limit,
                "referrer": referrer,
                "auto_fields": True,
                "auto_aggregations": True,
                "use_aggregate_conditions": True,
                "allow_metric_aggregates": allow_metric_aggregates,
            }
            if not metrics_enhanced and performance_dry_run_mep:
                sentry_sdk.set_tag("query.mep_compatible", False)
                metrics_enhanced_performance.query(dry_run=True, **query_details)
            return dataset.query(**query_details)

        with self.handle_query_errors():
            # Don't include cursor headers if the client won't be using them
            if request.GET.get("noPagination"):
                return Response(
                    self.handle_results_with_meta(
                        request,
                        organization,
                        params["project_id"],
                        data_fn(0, self.get_per_page(request)),
                    )
                )
            else:
                return self.paginate(
                    request=request,
                    paginator=GenericOffsetPaginator(data_fn=data_fn),
                    on_results=lambda results: self.handle_results_with_meta(
                        request, organization, params["project_id"], results
                    ),
                )


class OrganizationEventsEndpoint(OrganizationEventsV2EndpointBase):
    private = True

    def get(self, request: Request, organization) -> Response:
        if not self.has_feature(organization, request):
            return Response(status=404)

        try:
            params = self.get_snuba_params(request, organization)
        except NoProjects:
            return Response([])
        except InvalidParams as err:
            raise ParseError(err)

        referrer = request.GET.get("referrer")
        use_metrics = features.has(
            "organizations:performance-use-metrics", organization=organization, actor=request.user
        ) or features.has(
            "organizations:dashboards-mep", organization=organization, actor=request.user
        )
        performance_dry_run_mep = features.has(
            "organizations:performance-dry-run-mep", organization=organization, actor=request.user
        )

        # This param will be deprecated in favour of dataset
        if "metricsEnhanced" in request.GET:
            metrics_enhanced = request.GET.get("metricsEnhanced") == "1" and use_metrics
            dataset = discover if not metrics_enhanced else metrics_enhanced_performance
        else:
            dataset = self.get_dataset(request) if use_metrics else discover
            metrics_enhanced = dataset != discover

        sentry_sdk.set_tag("performance.metrics_enhanced", metrics_enhanced)
        allow_metric_aggregates = request.GET.get("preventMetricAggregates") != "1"
        # Force the referrer to "api.auth-token.events" for events requests authorized through a bearer token
        if request.auth:
            referrer = API_TOKEN_REFERRER
        elif referrer not in ALLOWED_EVENTS_REFERRERS:
            referrer = "api.organization-events"

        def data_fn(offset, limit):
            query_details = {
                "selected_columns": self.get_field_list(organization, request),
                "query": request.GET.get("query"),
                "params": params,
                "equations": self.get_equation_list(organization, request),
                "orderby": self.get_orderby(request),
                "offset": offset,
                "limit": limit,
                "referrer": referrer,
                "auto_fields": True,
                "auto_aggregations": True,
                "use_aggregate_conditions": True,
                "allow_metric_aggregates": allow_metric_aggregates,
                "transform_alias_to_input_format": True,
            }
            if not metrics_enhanced and performance_dry_run_mep:
                sentry_sdk.set_tag("query.mep_compatible", False)
                metrics_enhanced_performance.query(dry_run=True, **query_details)
            return dataset.query(**query_details)

        with self.handle_query_errors():
            # Don't include cursor headers if the client won't be using them
            if request.GET.get("noPagination"):
                return Response(
                    self.handle_results_with_meta(
                        request,
                        organization,
                        params["project_id"],
                        data_fn(0, self.get_per_page(request)),
                        standard_meta=True,
                    )
                )
            else:
                return self.paginate(
                    request=request,
                    paginator=GenericOffsetPaginator(data_fn=data_fn),
                    on_results=lambda results: self.handle_results_with_meta(
                        request,
                        organization,
                        params["project_id"],
                        results,
                        standard_meta=True,
                    ),
                )


class OrganizationEventsGeoEndpoint(OrganizationEventsV2EndpointBase):
    def has_feature(self, request: Request, organization):
        return features.has("organizations:dashboards-basic", organization, actor=request.user)

    def get(self, request: Request, organization) -> Response:
        if not self.has_feature(request, organization):
            return Response(status=404)

        try:
            params = self.get_snuba_params(request, organization)
        except NoProjects:
            return Response([])

        maybe_aggregate = request.GET.get("field")

        if not maybe_aggregate:
            raise ParseError(detail="No column selected")

        if not is_function(maybe_aggregate):
            raise ParseError(detail="Functions may only be given")

        referrer = request.GET.get("referrer")
        referrer = (
            referrer if referrer in ALLOWED_EVENTS_GEO_REFERRERS else "api.organization-events-geo"
        )

        def data_fn(offset, limit):
            return discover.query(
                selected_columns=["geo.country_code", maybe_aggregate],
                query=f"{request.GET.get('query', '')} has:geo.country_code",
                params=params,
                offset=offset,
                limit=limit,
                referrer=referrer,
                use_aggregate_conditions=True,
                orderby=self.get_orderby(request) or maybe_aggregate,
            )

        with self.handle_query_errors():
            # We don't need pagination, so we don't include the cursor headers
            return Response(
                self.handle_results_with_meta(
                    request,
                    organization,
                    params["project_id"],
                    # Expect Discover query output to be at most 251 rows, which corresponds
                    # to the number of possible two-letter country codes as defined in ISO 3166-1 alpha-2.
                    #
                    # There are 250 country codes from sentry/static/app/data/countryCodesMap.tsx
                    # plus events with no assigned country code.
                    data_fn(0, self.get_per_page(request, default_per_page=251, max_per_page=251)),
                )
            )
