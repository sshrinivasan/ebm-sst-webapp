export type Control =
  | "file" | "select" | "multiselect" | "toggle" | "number" | "date" | "table";

export interface TableColumn {
  key: string;
  label: string;
  control?: "text" | "number" | "select";
  choices?: string[];
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
  group?: string;   // optional grouping key; e.g. "sst" renders in a conditional SST section
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
