export type Control =
  | "file" | "select" | "multiselect" | "toggle" | "number" | "date" | "table"
  | "subarea_assigner";

export type TableColumnControl = "text" | "number" | "select" | "multiselect";

export interface TableColumn {
  key: string;
  label: string;
  control?: TableColumnControl;
  choices?: string[];
  options?: string;        // name of an option-list in the options map (e.g. "unique_all_sample_ids")
  options_by_row?: string; // for multiselect: the row field whose value keys a per-row option map (e.g. "subarea")
  options_param?: string;  // for multiselect: name of another param whose rows supply the label options
}

export interface InputSpec {
  name: string;
  kind: string;
  control: Control;
  label: string;
  tab: string;
  example?: unknown;
  default?: unknown;
  choices?: string[];
  options?: string; // name of an option-list produced by the engine
  prefill?: string; // e.g. "all" -> preselect every option once they load (multiselect)
  full?: boolean;   // override default full-row width for this field
  rows?: Record<string, unknown>[];  // default row data for table controls (file-derived)
  group?: string;   // optional grouping key; e.g. "sst" renders in a conditional SST section
  onLabel?: string;   // toggle control: label when on (default "Enabled")
  offLabel?: string;  // toggle control: label when off (default "Disabled")
  display_column?: string;
  value_column?: string;
  columns?: TableColumn[]; // for control === "table"
}

export interface TableData {
  columns: string[];
  rows: Record<string, unknown>[];
}

export interface OutputSpec { var: string; label: string; tab: string; }
export interface ChartSpec { var: string; label: string; tab: string; }
export interface TabSpec { id: string; title: string; }

export interface NavNode {
  id?: string;         // present on leaf nodes
  title: string;
  icon?: string;
  children?: NavNode[]; // present on group nodes
}

export interface DynamicOutputSpec {
  prefix: string;       // e.g. "texture_split_"
  tab: string;          // which tab these dynamic outputs appear on
  label_prefix?: string; // optional label prefix for the subtab title
}

export interface Schema {
  nav: NavNode[];
  tabs: TabSpec[];     // flat list of leaf tabs
  inputs: InputSpec[];
  outputs: OutputSpec[];
  charts: ChartSpec[];
  dynamic_outputs?: DynamicOutputSpec[];
  dynamic_charts?: DynamicOutputSpec[];
}

// options is a map of option-name -> string[] OR a TableData (for df options).
export type OptionMap = Record<string, string[] | TableData>;

export interface Notice {
  level: "error" | "warning" | "info" | "success";
  workflow?: string | null;
  message: string;
}

export interface RunResult {
  outputs: Record<string, TableData>;
  charts: Record<string, string>; // var -> data URI
  options: OptionMap;
  messages: Notice[];
  errors: { unit: string; error: string }[];
}

export type Params = Record<string, unknown>;
