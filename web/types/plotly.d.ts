declare module "plotly.js-dist-min" {
  // Hand-rolled ambient module: `plotly.js-dist-min` ships JS only and
  // `@types/plotly.js-dist-min` does not exist. The minified build has
  // the same runtime API as `plotly.js`, so this declaration covers the
  // narrow surface we actually use (Layout / Data / Config + newPlot /
  // purge / relayout). Extend as needed when new chart features land.
  export type Layout = Record<string, unknown> & {
    shapes?: unknown[];
    annotations?: unknown[];
    xaxis?: Record<string, unknown>;
    yaxis?: Record<string, unknown>;
    margin?: { l?: number; r?: number; t?: number; b?: number };
    paper_bgcolor?: string;
    plot_bgcolor?: string;
    font?: Record<string, unknown>;
    hovermode?: string;
    hoverlabel?: Record<string, unknown>;
    showlegend?: boolean;
    autosize?: boolean;
    title?: { text?: string; font?: Record<string, unknown> };
  };

  export type Data = Record<string, unknown> & {
    // ``string`` entries cover categorical / heatmap axes (e.g. group
    // labels); numeric entries cover line and scatter traces.
    x?: (number | string)[];
    // ``null`` entries render as gaps; callers use that to drop
    // non-positive samples from a log axis without breaking x/y
    // alignment.
    y?: (number | string | null)[];
    // ``null`` entries render as gaps; the log-scale heatmap uses that
    // to skip cells where ``v <= 0`` (log undefined).
    z?: (number | null)[][];
    type?: string;
    mode?: string;
    line?: Record<string, unknown>;
    marker?: Record<string, unknown>;
    fill?: string;
    fillcolor?: string;
    hovertemplate?: string;
    hoverinfo?: string;
    name?: string;
    connectgaps?: boolean;
    colorscale?: string | (number | string)[][];
    colorbar?: Record<string, unknown>;
    zsmooth?: false | "fast" | "best";
    showscale?: boolean;
    // Carries per-cell auxiliary values reachable from
    // ``hovertemplate`` via ``%{customdata}`` - heatmap traces use 2D,
    // line / scatter use 1D.
    customdata?: (number | string | null)[] | (number | string | null)[][];
  };

  export type Config = Record<string, unknown> & {
    responsive?: boolean;
    displaylogo?: boolean;
    displayModeBar?: boolean;
    modeBarButtonsToRemove?: string[];
    toImageButtonOptions?: Record<string, unknown>;
  };

  export function newPlot(
    el: HTMLElement,
    data: Data[],
    layout?: Partial<Layout>,
    config?: Partial<Config>,
  ): Promise<unknown>;

  export function purge(el: HTMLElement): void;

  export function relayout(
    el: HTMLElement,
    layout: Partial<Layout>,
  ): Promise<unknown>;

  const Plotly: {
    newPlot: typeof newPlot;
    purge: typeof purge;
    relayout: typeof relayout;
  };
  export default Plotly;
}
