// Dimension table types matching Supabase schema

export interface DimCategory {
  id: string;
  canonical_name: string;
  sipsa_id?: number;
}

export interface DimSubcategory {
  id: string;
  canonical_name: string;
  category_id: string;
}

export interface DimProduct {
  id: string;
  canonical_name: string;
  subcategory_id: string;
  cpc_code?: string;
  sipsa_id?: number;
}

export interface DimPresentation {
  id: string;
  canonical_name: string;
}

export interface DimUnits {
  id: string;
  canonical_name: string;
}

export interface DimDepartment {
  id: string;
  canonical_name: string;
  divipola_code?: string;
}

export interface DimCity {
  id: string;
  canonical_name: string;
  department_id: string;
  divipola_code?: string;
}

export interface DimMarket {
  id: string;
  canonical_name: string;
  city_id: string;
  sipsa_id?: number;
}

export interface DimCpc {
  code: string;
  title: string;
  level: 'section' | 'division' | 'group' | 'class' | 'subclass' | 'product';
  parent_code: string | null;
  section_code: string | null;
  division_code: string | null;
  group_code: string | null;
  class_code: string | null;
}

export interface DimInsumo {
  id: string;
  canonical_name: string;
  grupo?: string;
  subgrupo?: string;
  cpc_code?: string;
  cpc_id?: string;
  grupo_id?: string;
  subgrupo_id?: string;
  sipsa_id?: number;
}

export interface DimInsumoGrupo {
  id: string;
  canonical_name: string;
}

export interface DimInsumoSubgrupo {
  id: string;
  canonical_name: string;
  grupo_id: string;
}

export interface PriceObservation {
  id: string;
  price_date: string;
  round: number;
  min_price: number | null;
  max_price: number | null;
  avg_price: number | null;
  category_id: string;
  subcategory_id: string;
  product_id: string;
  presentation_id: string | null;
  units_id: string | null;
  department_id: string;
  city_id: string;
  market_id: string | null;
}

export interface SupplyObservation {
  id: string;
  observation_date: string;
  city_id: string;
  market_id: string | null;
  provenance_dept_code: string | null;
  provenance_muni_code: string | null;
  provenance_dept_name: string | null;
  provenance_muni_name: string | null;
  category_id: string;
  product_id: string;
  cpc_code: string | null;
  quantity_kg: number;
}

export interface InsumoMunicipalityPrice {
  id: string;
  price_date: string;
  department_id: string;
  city_id: string | null;
  insumo_id: string;
  presentation: string | null;
  avg_price: number | null;
  grupo_id: string | null;
  subgrupo_id: string | null;
}

export interface InsumoDepartmentPrice {
  id: string;
  price_date: string;
  department_id: string;
  insumo_id: string;
  articulo: string | null;
  casa_comercial_id: string | null;
  cpc_code: string | null;
  presentation: string | null;
  avg_price: number | null;
  grupo_id: string | null;
  subgrupo_id: string | null;
}

export interface ProductWithDetails extends DimProduct {
  category_name?: string;
  subcategory_name?: string;
  latest_min_price?: number;
  latest_max_price?: number;
  latest_avg_price?: number;
  price_change_pct?: number;
}

export interface MarketWithDetails extends DimMarket {
  city_name?: string;
  department_name?: string;
  product_count?: number;
}

export interface InsumoWithDetails extends DimInsumo {
  grupo_name?: string;
  subgrupo_name?: string;
  latest_avg_price?: number;
  price_change_pct?: number;
}
