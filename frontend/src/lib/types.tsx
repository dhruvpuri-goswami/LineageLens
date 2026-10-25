import {
  BarChart3, Boxes, Calculator, Database, FileBarChart2, Layers, LayoutPanelTop, ShieldCheck, SlidersHorizontal,
  Sigma, Snowflake, Table2, Package, type LucideIcon,
} from 'lucide-react'

export interface TypeMeta {
  label: string
  short: string
  icon: LucideIcon
  layer: 'source' | 'dbt' | 'snowflake' | 'model' | 'report'
  color: string // tailwind text color
  bg: string // tailwind bg tint
  hex: string
}

export const TYPE_META: Record<string, TypeMeta> = {
  dbt_source_column: { label: 'dbt source column', short: 'Source', icon: Database, layer: 'source', color: 'text-slate-600 dark:text-slate-300', bg: 'bg-slate-500/10', hex: '#64748b' },
  dbt_model_column: { label: 'dbt model column', short: 'dbt', icon: Boxes, layer: 'dbt', color: 'text-orange-600 dark:text-orange-400', bg: 'bg-orange-500/10', hex: '#f97316' },
  snowflake_table_column: { label: 'Snowflake table column', short: 'Table', icon: Snowflake, layer: 'snowflake', color: 'text-sky-600 dark:text-sky-400', bg: 'bg-sky-500/10', hex: '#0ea5e9' },
  snowflake_view_column: { label: 'Snowflake view column', short: 'View', icon: Snowflake, layer: 'snowflake', color: 'text-sky-600 dark:text-sky-400', bg: 'bg-sky-500/10', hex: '#0284c7' },
  pbi_model_column: { label: 'Power BI column', short: 'Column', icon: Table2, layer: 'model', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-500/10', hex: '#f59e0b' },
  calc_column: { label: 'Calculated column', short: 'Calc col', icon: Calculator, layer: 'model', color: 'text-yellow-700 dark:text-yellow-400', bg: 'bg-yellow-500/10', hex: '#ca8a04' },
  measure: { label: 'Measure', short: 'Measure', icon: Sigma, layer: 'model', color: 'text-violet-600 dark:text-violet-400', bg: 'bg-violet-500/10', hex: '#8b5cf6' },
  rls_role: { label: 'RLS role', short: 'RLS', icon: ShieldCheck, layer: 'model', color: 'text-rose-600 dark:text-rose-400', bg: 'bg-rose-500/10', hex: '#f43f5e' },
  calc_group_item: { label: 'Calculation item', short: 'Calc item', icon: Layers, layer: 'model', color: 'text-fuchsia-600 dark:text-fuchsia-400', bg: 'bg-fuchsia-500/10', hex: '#d946ef' },
  field_parameter: { label: 'Field parameter', short: 'Field param', icon: SlidersHorizontal, layer: 'model', color: 'text-teal-600 dark:text-teal-400', bg: 'bg-teal-500/10', hex: '#14b8a6' },
  visual: { label: 'Visual', short: 'Visual', icon: BarChart3, layer: 'report', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-500/10', hex: '#10b981' },
  page: { label: 'Page', short: 'Page', icon: LayoutPanelTop, layer: 'report', color: 'text-emerald-700 dark:text-emerald-300', bg: 'bg-emerald-500/10', hex: '#059669' },
  report: { label: 'Report', short: 'Report', icon: FileBarChart2, layer: 'report', color: 'text-green-700 dark:text-green-300', bg: 'bg-green-500/10', hex: '#16a34a' },
  semantic_model: { label: 'Semantic model', short: 'Model', icon: Package, layer: 'model', color: 'text-amber-700 dark:text-amber-300', bg: 'bg-amber-500/10', hex: '#d97706' },
}

export const meta = (t: string): TypeMeta => TYPE_META[t] ?? TYPE_META.dbt_model_column

export const WAREHOUSE = ['dbt_source_column', 'dbt_model_column', 'snowflake_table_column', 'snowflake_view_column']
export const MODEL_TYPES = ['pbi_model_column', 'calc_column', 'measure', 'rls_role', 'calc_group_item', 'field_parameter']
