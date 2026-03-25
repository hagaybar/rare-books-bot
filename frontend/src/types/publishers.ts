export interface PublisherVariant {
  id?: number;
  variant_form: string;
  script: string;
  language: string | null;
  is_primary: boolean;
}

export interface PublisherAuthority {
  id: number;
  canonical_name: string;
  type: string;
  confidence: number;
  dates_active: string | null;
  location: string | null;
  is_missing_marker: boolean;
  variant_count: number;
  imprint_count: number;
  variants: PublisherVariant[];
  viaf_id: string | null;
  wikidata_id: string | null;
  cerl_id: string | null;
}

export interface PublisherAuthorityListResponse {
  total: number;
  items: PublisherAuthority[];
}
