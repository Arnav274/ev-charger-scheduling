import { useMemo, useRef } from "react";

// For requests where only the most recent answer should be used: claim() a
// number when sending, and check isLatest(number) before using the response.
export default function useLatestRequest() {
  const latest = useRef(0);
  return useMemo(
    () => ({
      claim: () => ++latest.current,
      isLatest: (request) => request === latest.current,
      // Makes every request in flight stale.
      cancel: () => {
        latest.current += 1;
      },
    }),
    [],
  );
}
