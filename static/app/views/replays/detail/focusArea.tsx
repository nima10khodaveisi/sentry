import {useMemo} from 'react';

import Spans from 'sentry/components/events/interfaces/spans';
import Placeholder from 'sentry/components/placeholder';
import {useReplayContext} from 'sentry/components/replays/replayContext';
import TagsTable from 'sentry/components/tagsTable';
import type {RawCrumb} from 'sentry/types/breadcrumbs';
import {isBreadcrumbTypeDefault} from 'sentry/types/breadcrumbs';
import type {EventTransaction} from 'sentry/types/event';
import {EntryType} from 'sentry/types/event';
import ReplayReader from 'sentry/utils/replays/replayReader';
import useOrganization from 'sentry/utils/useOrganization';

import Console from './console';
import IssueList from './issueList';
import MemoryChart from './memoryChart';
import Trace from './trace';
import useActiveTabFromLocation from './useActiveTabFromLocation';

type Props = {
  replay: ReplayReader | null;
};

function getBreadcrumbsByCategory(breadcrumbs: RawCrumb[], categories: string[]) {
  return breadcrumbs
    .filter(isBreadcrumbTypeDefault)
    .filter(breadcrumb => categories.includes(breadcrumb.category || ''));
}

function FocusArea({replay}: Props) {
  const active = useActiveTabFromLocation();
  const {currentTime, currentHoverTime, setCurrentTime, setCurrentHoverTime} =
    useReplayContext();
  const organization = useOrganization();

  // Memoize this because re-renders will interfere with the mouse state of the
  // chart (e.g. on mouse over and out)
  const memorySpans = useMemo(() => {
    return replay?.getRawSpans().filter(replay.isMemorySpan);
  }, [replay]);

  if (!replay || !memorySpans) {
    return <Placeholder height="150px" />;
  }

  const event = replay.getEvent();

  switch (active) {
    case 'console':
      const consoleMessages = getBreadcrumbsByCategory(replay?.getRawCrumbs(), [
        'console',
      ]);
      return (
        <Console
          breadcrumbs={consoleMessages ?? []}
          startTimestamp={event?.startTimestamp}
        />
      );
    case 'network': {
      // Fake the span and Trace context
      const nonMemorySpansEntry = {
        type: EntryType.SPANS,
        data: replay
          .getRawSpans()
          .filter(replay.isNotMemorySpan)
          .map(({startTimestamp, endTimestamp, ...span}) => ({
            ...span,
            timestamp: endTimestamp,
            start_timestamp: startTimestamp,
            parent_span_id: 'replay_network_trace',
          })),
      };
      const performanceEvent = {
        ...event,
        contexts: {
          trace: {
            type: 'trace',
            op: 'Network',
            description: 'WIP',
            span_id: 'replay_network_trace',
            status: 'ok',
          },
        },
        entries: [nonMemorySpansEntry],
      } as EventTransaction;
      return <Spans organization={organization} event={performanceEvent} />;
    }
    case 'trace':
      return <Trace organization={organization} event={event} />;
    case 'issues':
      return <IssueList replayId={event.id} projectId={event.projectID} />;
    case 'tags':
      return <TagsTable generateUrl={() => ''} event={event} query="" />;
    case 'memory':
      return (
        <MemoryChart
          currentTime={currentTime}
          currentHoverTime={currentHoverTime}
          memorySpans={memorySpans}
          setCurrentTime={setCurrentTime}
          setCurrentHoverTime={setCurrentHoverTime}
          startTimestamp={event?.startTimestamp}
        />
      );
    default:
      return null;
  }
}

export default FocusArea;
