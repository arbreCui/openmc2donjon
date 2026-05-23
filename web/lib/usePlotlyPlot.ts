"use client";

/**
 * Shared lifecycle hook for inline Plotly cards. Caller passes a
 * ``build()`` that returns ``{traces, layout, config?}`` (or null to
 * skip rendering) and a deps array; gets back a ref to attach to a
 * ``<div>``.
 *
 *   const ref = usePlotlyPlot(
 *     () => ({ traces, layout, config }),
 *     [data, mixture, scale],
 *   );
 *   return <div ref={ref} className="h-80" />;
 *
 * Plotly is loaded via dynamic import so server-side rendering and the
 * initial bundle aren't blocked on a ~3 MB chart library; the chart
 * appears once the module resolves. Errors surface inline rather than
 * leaving a silent empty box.
 */

import { useEffect, useRef, type DependencyList, type RefObject } from "react";
import type { Data, Layout, Config } from "plotly.js-dist-min";

type PlotlyModule = {
  newPlot: (
    el: HTMLElement,
    data: Data[],
    layout: Partial<Layout>,
    config?: Partial<Config>,
  ) => Promise<unknown>;
  purge: (el: HTMLElement) => void;
};

export type PlotSpec = {
  traces: Data[];
  layout: Partial<Layout>;
  config?: Partial<Config>;
};

const DEFAULT_CONFIG: Partial<Config> = {
  responsive: true,
  displaylogo: false,
  displayModeBar: false,
};

function renderError(host: HTMLDivElement, msg: string) {
  // Construct the error box with DOM APIs and ``textContent`` rather
  // than ``innerHTML``: the message comes from a thrown exception, which
  // could in principle include arbitrary characters. Even in a
  // localhost-only tool, ``textContent`` keeps "<", ">", and quotes
  // inert instead of trusting the runtime to never produce HTML.
  host.replaceChildren();
  const box = host.ownerDocument.createElement("div");
  box.style.cssText =
    "padding:1rem;font:11px/1.5 -apple-system,sans-serif;color:#fca5a5;" +
    "background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.25);" +
    "border-radius:8px";
  box.textContent = `plot failed: ${msg}`;
  host.appendChild(box);
}

export function usePlotlyPlot(
  build: () => PlotSpec | null,
  deps: DependencyList,
): RefObject<HTMLDivElement | null> {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    let disposed = false;
    let Plotly: PlotlyModule | null = null;
    import("plotly.js-dist-min")
      .then((mod) => {
        if (disposed) return;
        Plotly = (mod.default ?? mod) as unknown as PlotlyModule;
        const spec = build();
        if (!spec) return;
        return Plotly.newPlot(
          host,
          spec.traces,
          spec.layout,
          spec.config ?? DEFAULT_CONFIG,
        );
      })
      .catch((e) => {
        if (disposed || !ref.current) return;
        // Surface the failure instead of leaving an empty box. Common
        // causes: bundler chunk load fail, browser OOM with huge traces,
        // an exception inside Plotly's autotype detection on bad data.
        renderError(ref.current, String(e?.message ?? e));
      });
    return () => {
      disposed = true;
      // ``host`` is the node we drew into; ``ref.current`` may already
      // point at the next render's DOM. Purging ``host`` keeps the
      // teardown bound to the same element we plotted into.
      if (Plotly) {
        try {
          Plotly.purge(host);
        } catch {
          /* ignore */
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}
