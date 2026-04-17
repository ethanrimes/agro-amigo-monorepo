export type Locale = 'es' | 'en';

export interface Translations {
  // Navigation
  nav_home: string;
  nav_home_tab: string;
  nav_products: string;
  nav_markets: string;
  nav_inputs: string;
  nav_map: string;
  nav_settings: string;
  nav_product: string;
  nav_market: string;
  nav_input: string;

  // Settings
  settings_default_market: string;
  settings_default_market_desc: string;
  settings_national_avg: string;
  settings_department: string;
  settings_city: string;
  settings_specific_market: string;
  settings_select_option: string;
  settings_no_results: string;
  settings_showing_n_of: string;
  settings_search_placeholder: string;
  settings_font_size: string;
  settings_font_size_desc: string;
  settings_font_small: string;
  settings_font_normal: string;
  settings_font_large: string;
  settings_font_xlarge: string;
  settings_preview: string;
  settings_preview_desc: string;
  settings_language: string;
  settings_language_desc: string;
  settings_charts: string;
  settings_charts_desc: string;
  settings_chart_avg_line: string;
  settings_chart_trend_line: string;
  settings_chart_min_max_callouts: string;
  settings_chart_interactive: string;

  // Product detail - extra
  product_vs_prev_week: string;
  product_national_avg: string;
  product_daily_avg: string;
  product_total_sum: string;
  product_pct_total: string;
  product_sort_asc: string;
  product_sort_desc: string;
  product_median: string;
  product_mean: string;

  // Home
  home_loading: string;
  home_watchlist: string;
  home_no_recent_data: string;
  home_categories: string;
  home_top_increases: string;
  home_top_decreases: string;
  home_top_supply: string;
  home_last_week: string;
  home_last_7_days: string;
  home_help_methodology: string;
  home_market_info_title: string;
  home_market_info_text: string;
  home_market_info_change: string;
  home_understood: string;
  home_help: string;
  home_app_guide: string;
  home_help_home_text: string;
  home_help_products_text: string;
  home_help_markets_text: string;
  home_help_inputs_text: string;
  home_help_map_text: string;
  home_sources_methodology: string;
  home_sources_text: string;
  home_disclaimer: string;

  // Products page
  products_search: string;
  products_all: string;
  products_not_found: string;

  // Insumos page
  inputs_search: string;
  inputs_all: string;
  inputs_not_found: string;

  // Markets page
  markets_search: string;
  markets_not_found: string;

  // Product detail
  product_not_found: string;
  product_price_section: string;
  product_prices: string;
  product_filters: string;
  product_all_markets: string;
  product_all_presentations: string;
  product_min: string;
  product_avg: string;
  product_max: string;
  product_no_price_data: string;
  product_prices_by_market: string;
  product_prices_by_market_note: string;
  product_market_fallback: string;
  product_supply_section: string;
  product_supply: string;
  product_total: string;
  product_no_supply_data: string;
  product_provenance: string;
  product_provenance_subtitle: string;
  product_unknown: string;
  product_price_at: string;

  // Time ranges
  time_1w: string;
  time_1m: string;
  time_3m: string;
  time_6m: string;
  time_1y: string;
  time_all: string;

  // Insumo detail
  input_not_found: string;
  input_departments: string;
  input_municipalities: string;
  input_department_count: string;
  input_municipality_count: string;
  input_price_history: string;
  input_price_by_dept: string;
  input_no_data: string;
  input_unknown: string;
  input_price_detail: string;
  input_presentation: string;

  // Market detail
  market_not_found: string;
  market_products: string;
  market_categories: string;
  market_recent_products: string;
  market_prices_at: string;
  market_no_recent_data: string;
  market_product_fallback: string;

  // Market comparator
  compare_prices_title: string;
  compare_supply_title: string;
  compare_national_avg: string;
  compare_all_markets: string;
  compare_search_market: string;
  compare_select_market: string;
  compare_product: string;
  compare_diff: string;
  compare_no_match: string;
  compare_no_results: string;
  compare_matching: string;
  compare_overall_avg: string;
  compare_loading: string;
  compare_observed: string;

  // Map
  map_prices: string;
  map_supply: string;
  map_loading: string;
  map_price_legend: string;
  map_supply_legend: string;
  map_no_data: string;
  map_source: string;
  map_select_product: string;
  map_search_product: string;
  map_all_products: string;
  map_no_highlight_note: string;

  // Auth
  auth_sign_in: string;
  auth_sign_up: string;
  auth_sign_out: string;
  auth_create_account: string;
  auth_sign_in_desc: string;
  auth_create_account_desc: string;
  auth_username: string;
  auth_email: string;
  auth_password: string;
  auth_fill_all_fields: string;
  auth_username_too_short: string;
  auth_username_taken: string;
  auth_signup_success: string;
  auth_error: string;
  auth_account: string;
  auth_member_since: string;
  auth_go_back: string;
  auth_signed_in_as: string;

  // Comments
  comments_title: string;
  comments_placeholder: string;
  comments_sign_in_to_comment: string;
  comments_loading: string;
  comments_empty: string;
  comments_error: string;
  comments_anonymous: string;
  comments_latest: string;
  comments_on_product: string;
  comments_on_market: string;
  comments_on_insumo: string;

  // Settings - comments & account
  settings_comments: string;
  settings_comments_desc: string;
  settings_comments_toggle: string;
  settings_account: string;
  settings_account_desc: string;
  settings_sign_in: string;

  // Search
  search_placeholder: string;
}

export const es: Translations = {
  // Navigation
  nav_home: 'AgroAmigo',
  nav_home_tab: 'Inicio',
  nav_products: 'Productos',
  nav_markets: 'Mercados',
  nav_inputs: 'Insumos',
  nav_map: 'Mapa',
  nav_settings: 'Configuraci\u00f3n',
  nav_product: 'Producto',
  nav_market: 'Mercado',
  nav_input: 'Insumo',

  // Settings
  settings_default_market: 'Mercado predeterminado',
  settings_default_market_desc: 'Define qu\u00e9 precios se muestran en la pantalla de inicio.',
  settings_national_avg: 'Promedio nacional',
  settings_department: 'Departamento',
  settings_city: 'Ciudad',
  settings_specific_market: 'Mercado espec\u00edfico',
  settings_select_option: 'Selecciona una opci\u00f3n',
  settings_no_results: 'Sin resultados',
  settings_showing_n_of: 'Mostrando 50 de',
  settings_search_placeholder: 'Buscar',
  settings_font_size: 'Tama\u00f1o de texto',
  settings_font_size_desc: 'Ajusta el tama\u00f1o de la tipograf\u00eda.',
  settings_font_small: 'Peque\u00f1o',
  settings_font_normal: 'Normal',
  settings_font_large: 'Grande',
  settings_font_xlarge: 'Muy grande',
  settings_preview: 'Vista previa',
  settings_preview_desc: 'As\u00ed se ver\u00e1 el texto con el tama\u00f1o seleccionado.',
  settings_language: 'Idioma',
  settings_language_desc: 'Cambia el idioma de la aplicaci\u00f3n.',
  settings_charts: 'Gr\u00e1ficos',
  settings_charts_desc: 'Configura las opciones de los gr\u00e1ficos de l\u00ednea.',
  settings_chart_avg_line: 'L\u00ednea promedio',
  settings_chart_trend_line: 'L\u00ednea de tendencia',
  settings_chart_min_max_callouts: 'Anotaciones m\u00edn/m\u00e1x',
  settings_chart_interactive: 'Callout interactivo',

  product_vs_prev_week: 'vs. semana anterior',
  product_national_avg: 'Promedio nacional',
  product_daily_avg: 'Promedio diario',
  product_total_sum: 'Total',
  product_pct_total: '% del total',
  product_sort_asc: 'Ascendente',
  product_sort_desc: 'Descendente',
  product_median: 'Mediana',
  product_mean: 'Promedio',

  // Home
  home_loading: 'Cargando datos...',
  home_watchlist: 'Seguimiento',
  home_no_recent_data: 'Sin datos recientes',
  home_categories: 'Categor\u00edas',
  home_top_increases: 'Mayores alzas',
  home_top_decreases: 'Mayores bajas',
  home_top_supply: 'Mayor abastecimiento',
  home_last_week: '\u00daltima semana',
  home_last_7_days: '\u00daltimos 7 d\u00edas',
  home_help_methodology: 'Ayuda y metodolog\u00eda',
  home_market_info_title: 'Mercado predeterminado',
  home_market_info_text: 'Los precios que ves en la pantalla de inicio provienen de tu mercado predeterminado:',
  home_market_info_change: 'Puedes cambiar tu mercado en',
  home_understood: 'Entendido',
  home_help: 'Ayuda',
  home_app_guide: 'Gu\u00eda de la aplicaci\u00f3n',
  home_help_home_text: 'Tu panel principal con seguimiento, categor\u00edas y movimientos del mercado.',
  home_help_products_text: 'M\u00e1s de 700 productos con precios hist\u00f3ricos y comparaci\u00f3n entre mercados.',
  home_help_markets_text: '43 mercados mayoristas y 500+ mercados municipales.',
  home_help_inputs_text: 'Precios de 2,000+ insumos agropecuarios por departamento.',
  home_help_map_text: 'Visualiza precios y flujos de abastecimiento sobre el mapa de Colombia.',
  home_sources_methodology: 'Fuentes y metodolog\u00eda',
  home_sources_text: 'Todos los datos provienen del SIPSA (Sistema de Informaci\u00f3n de Precios y Abastecimiento del Sector Agropecuario), operado por el DANE de Colombia.',
  home_disclaimer: 'Esta aplicaci\u00f3n no es un producto oficial del DANE.',

  // Products page
  products_search: 'Buscar producto...',
  products_all: 'Todos',
  products_not_found: 'No se encontraron productos',

  // Insumos page
  inputs_search: 'Buscar insumo...',
  inputs_all: 'Todos',
  inputs_not_found: 'No se encontraron insumos',

  // Markets page
  markets_search: 'Buscar mercado o ciudad...',
  markets_not_found: 'No se encontraron mercados',

  // Product detail
  product_not_found: 'Producto no encontrado',
  product_price_section: 'Precios',
  product_prices: 'Precios',
  product_filters: 'Filtros',
  product_all_markets: 'Todos',
  product_all_presentations: 'Todas',
  product_min: 'M\u00edn',
  product_avg: 'Prom',
  product_max: 'M\u00e1x',
  product_no_price_data: 'Sin datos de precios para este per\u00edodo',
  product_prices_by_market: 'Precios por mercado',
  product_prices_by_market_note: 'Precios m\u00e1s recientes de cada mercado.',
  product_market_fallback: 'Mercado',
  product_supply_section: 'Abastecimiento',
  product_supply: 'Abastecimiento',
  product_total: 'Total',
  product_no_supply_data: 'Sin datos de abastecimiento',
  product_provenance: 'Procedencia',
  product_provenance_subtitle: 'Departamentos de origen',
  product_unknown: 'Desconocido',
  product_price_at: 'Precio al',

  // Time ranges
  time_1w: '1S',
  time_1m: '1M',
  time_3m: '3M',
  time_6m: '6M',
  time_1y: '1A',
  time_all: 'Todo',

  // Insumo detail
  input_not_found: 'Insumo no encontrado',
  input_departments: 'Departamentos',
  input_municipalities: 'Municipios',
  input_department_count: 'Departamento',
  input_municipality_count: 'Municipio',
  input_price_history: 'Precio promedio en el tiempo',
  input_price_by_dept: 'Precio por departamento',
  input_no_data: 'Sin datos',
  input_unknown: 'Desconocido',
  input_price_detail: 'Detalle de precios',
  input_presentation: 'Presentaci\u00f3n',

  // Market detail
  market_not_found: 'Mercado no encontrado',
  market_products: 'Productos',
  market_categories: 'Categor\u00edas',
  market_recent_products: 'Productos recientes',
  market_prices_at: 'Precios al',
  market_no_recent_data: 'Sin datos recientes',
  market_product_fallback: 'Producto',

  // Market comparator
  compare_prices_title: 'Comparar precios',
  compare_supply_title: 'Comparar abastecimiento',
  compare_national_avg: 'Promedio nacional',
  compare_all_markets: 'Promedio de todos los mercados',
  compare_search_market: 'Buscar mercado...',
  compare_select_market: 'Selecciona un mercado para comparar',
  compare_product: 'Producto',
  compare_diff: 'Dif',
  compare_no_match: 'No se encontraron productos en com\u00fan',
  compare_no_results: 'No se encontraron mercados',
  compare_matching: 'productos en com\u00fan',
  compare_overall_avg: 'Promedio general',
  compare_loading: 'Cargando comparaci\u00f3n...',
  compare_observed: 'Observado el',

  // Map
  map_prices: 'Precios',
  map_supply: 'Abastecimiento',
  map_loading: 'Cargando mapa...',
  map_price_legend: 'Precio promedio por departamento (30 d\u00edas)',
  map_supply_legend: 'Volumen de abastecimiento por departamento (30 d\u00edas)',
  map_no_data: 'Sin datos',
  map_source: 'Fuente: SIPSA-DANE',
  map_select_product: 'Seleccionar producto',
  map_search_product: 'Buscar producto...',
  map_all_products: 'Todos los productos',
  map_no_highlight_note: 'Si no se resaltan departamentos o mercados, no hay datos para este producto en los \u00faltimos 30 d\u00edas.',

  // Auth
  auth_sign_in: 'Iniciar sesi\u00f3n',
  auth_sign_up: 'Crear cuenta',
  auth_sign_out: 'Cerrar sesi\u00f3n',
  auth_create_account: 'Crear cuenta',
  auth_sign_in_desc: 'Inicia sesi\u00f3n para dejar comentarios.',
  auth_create_account_desc: 'Crea una cuenta para participar en la comunidad.',
  auth_username: 'Nombre de usuario',
  auth_email: 'Correo electr\u00f3nico',
  auth_password: 'Contrase\u00f1a',
  auth_fill_all_fields: 'Completa todos los campos',
  auth_username_too_short: 'El nombre de usuario debe tener al menos 3 caracteres',
  auth_username_taken: 'Este nombre de usuario ya est\u00e1 en uso',
  auth_signup_success: 'Cuenta creada. Revisa tu correo para confirmar.',
  auth_error: 'Error de autenticaci\u00f3n',
  auth_account: 'Mi cuenta',
  auth_member_since: 'Miembro desde',
  auth_go_back: 'Volver',
  auth_signed_in_as: 'Conectado como',

  // Comments
  comments_title: 'Comentarios',
  comments_placeholder: 'Escribe un comentario...',
  comments_sign_in_to_comment: 'Inicia sesi\u00f3n para comentar',
  comments_loading: 'Cargando comentarios...',
  comments_empty: 'A\u00fan no hay comentarios. S\u00e9 el primero.',
  comments_error: 'Error al publicar comentario',
  comments_anonymous: 'An\u00f3nimo',
  comments_latest: '\u00daltimos comentarios',
  comments_on_product: 'en producto',
  comments_on_market: 'en mercado',
  comments_on_insumo: 'en insumo',

  // Settings - comments & account
  settings_comments: 'Comentarios',
  settings_comments_desc: 'Activa o desactiva la secci\u00f3n de comentarios en la aplicaci\u00f3n.',
  settings_comments_toggle: 'Mostrar comentarios',
  settings_account: 'Cuenta',
  settings_account_desc: 'Inicia sesi\u00f3n para dejar comentarios.',
  settings_sign_in: 'Iniciar sesi\u00f3n',

  // Search
  search_placeholder: 'Buscar...',
};

export const en: Translations = {
  // Navigation
  nav_home: 'AgroAmigo',
  nav_home_tab: 'Home',
  nav_products: 'Products',
  nav_markets: 'Markets',
  nav_inputs: 'Inputs',
  nav_map: 'Map',
  nav_settings: 'Settings',
  nav_product: 'Product',
  nav_market: 'Market',
  nav_input: 'Input',

  // Settings
  settings_default_market: 'Default market',
  settings_default_market_desc: 'Choose which prices appear on the home screen.',
  settings_national_avg: 'National average',
  settings_department: 'Department',
  settings_city: 'City',
  settings_specific_market: 'Specific market',
  settings_select_option: 'Select an option',
  settings_no_results: 'No results',
  settings_showing_n_of: 'Showing 50 of',
  settings_search_placeholder: 'Search',
  settings_font_size: 'Text size',
  settings_font_size_desc: 'Adjust the font size.',
  settings_font_small: 'Small',
  settings_font_normal: 'Normal',
  settings_font_large: 'Large',
  settings_font_xlarge: 'Extra large',
  settings_preview: 'Preview',
  settings_preview_desc: 'This is how text will look at the selected size.',
  settings_language: 'Language',
  settings_language_desc: 'Change the app language.',
  settings_charts: 'Charts',
  settings_charts_desc: 'Configure line chart display options.',
  settings_chart_avg_line: 'Average line',
  settings_chart_trend_line: 'Trend line',
  settings_chart_min_max_callouts: 'Min/max callouts',
  settings_chart_interactive: 'Interactive callout',

  product_vs_prev_week: 'vs. previous week',
  product_national_avg: 'National average',
  product_daily_avg: 'Daily average',
  product_total_sum: 'Total',
  product_pct_total: '% of total',
  product_sort_asc: 'Ascending',
  product_sort_desc: 'Descending',
  product_median: 'Median',
  product_mean: 'Mean',

  // Home
  home_loading: 'Loading data...',
  home_watchlist: 'Watchlist',
  home_no_recent_data: 'No recent data',
  home_categories: 'Categories',
  home_top_increases: 'Top increases',
  home_top_decreases: 'Top decreases',
  home_top_supply: 'Top supply',
  home_last_week: 'Last week',
  home_last_7_days: 'Last 7 days',
  home_help_methodology: 'Help & methodology',
  home_market_info_title: 'Default market',
  home_market_info_text: 'The prices on the home screen come from your default market:',
  home_market_info_change: 'You can change your market in',
  home_understood: 'Got it',
  home_help: 'Help',
  home_app_guide: 'App guide',
  home_help_home_text: 'Your main dashboard with watchlist, categories, and market movements.',
  home_help_products_text: 'Over 700 products with historical prices and market comparisons.',
  home_help_markets_text: '43 wholesale markets and 500+ municipal markets.',
  home_help_inputs_text: 'Prices for 2,000+ agricultural inputs by department.',
  home_help_map_text: 'Visualize prices and supply flows on the map of Colombia.',
  home_sources_methodology: 'Sources & methodology',
  home_sources_text: 'All data comes from SIPSA (Agricultural Price and Supply Information System), operated by DANE of Colombia.',
  home_disclaimer: 'This application is not an official DANE product.',

  // Products page
  products_search: 'Search product...',
  products_all: 'All',
  products_not_found: 'No products found',

  // Insumos page
  inputs_search: 'Search input...',
  inputs_all: 'All',
  inputs_not_found: 'No inputs found',

  // Markets page
  markets_search: 'Search market or city...',
  markets_not_found: 'No markets found',

  // Product detail
  product_not_found: 'Product not found',
  product_price_section: 'Prices',
  product_prices: 'Prices',
  product_filters: 'Filters',
  product_all_markets: 'All',
  product_all_presentations: 'All',
  product_min: 'Min',
  product_avg: 'Avg',
  product_max: 'Max',
  product_no_price_data: 'No price data for this period',
  product_prices_by_market: 'Prices by market',
  product_prices_by_market_note: 'Latest prices from each market.',
  product_market_fallback: 'Market',
  product_supply_section: 'Supply',
  product_supply: 'Supply',
  product_total: 'Total',
  product_no_supply_data: 'No supply data',
  product_provenance: 'Provenance',
  product_provenance_subtitle: 'Departments of origin',
  product_unknown: 'Unknown',
  product_price_at: 'Price as of',

  // Time ranges
  time_1w: '1W',
  time_1m: '1M',
  time_3m: '3M',
  time_6m: '6M',
  time_1y: '1Y',
  time_all: 'All',

  // Insumo detail
  input_not_found: 'Input not found',
  input_departments: 'Departments',
  input_municipalities: 'Municipalities',
  input_department_count: 'Department',
  input_municipality_count: 'Municipality',
  input_price_history: 'Average price over time',
  input_price_by_dept: 'Price by department',
  input_no_data: 'No data',
  input_unknown: 'Unknown',
  input_price_detail: 'Price detail',
  input_presentation: 'Presentation',

  // Market detail
  market_not_found: 'Market not found',
  market_products: 'Products',
  market_categories: 'Categories',
  market_recent_products: 'Recent products',
  market_prices_at: 'Prices as of',
  market_no_recent_data: 'No recent data',
  market_product_fallback: 'Product',

  // Market comparator
  compare_prices_title: 'Compare prices',
  compare_supply_title: 'Compare supply',
  compare_national_avg: 'National average',
  compare_all_markets: 'Average across all markets',
  compare_search_market: 'Search market...',
  compare_select_market: 'Select a market to compare',
  compare_product: 'Product',
  compare_diff: 'Diff',
  compare_no_match: 'No matching products found',
  compare_no_results: 'No markets found',
  compare_matching: 'matching products',
  compare_overall_avg: 'Overall average',
  compare_loading: 'Loading comparison...',
  compare_observed: 'Observed',

  // Map
  map_prices: 'Prices',
  map_supply: 'Supply',
  map_loading: 'Loading map...',
  map_price_legend: 'Average price by department (30 days)',
  map_supply_legend: 'Supply volume by department (30 days)',
  map_no_data: 'No data',
  map_source: 'Source: SIPSA-DANE',
  map_select_product: 'Select product',
  map_search_product: 'Search product...',
  map_all_products: 'All products',
  map_no_highlight_note: 'If no departments or markets are highlighted, there is no data for this product in the last 30 days.',

  // Auth
  auth_sign_in: 'Sign in',
  auth_sign_up: 'Sign up',
  auth_sign_out: 'Sign out',
  auth_create_account: 'Create account',
  auth_sign_in_desc: 'Sign in to leave comments.',
  auth_create_account_desc: 'Create an account to join the community.',
  auth_username: 'Username',
  auth_email: 'Email',
  auth_password: 'Password',
  auth_fill_all_fields: 'Please fill all fields',
  auth_username_too_short: 'Username must be at least 3 characters',
  auth_username_taken: 'This username is already taken',
  auth_signup_success: 'Account created. Check your email to confirm.',
  auth_error: 'Authentication error',
  auth_account: 'My account',
  auth_member_since: 'Member since',
  auth_go_back: 'Go back',
  auth_signed_in_as: 'Signed in as',

  // Comments
  comments_title: 'Comments',
  comments_placeholder: 'Write a comment...',
  comments_sign_in_to_comment: 'Sign in to comment',
  comments_loading: 'Loading comments...',
  comments_empty: 'No comments yet. Be the first.',
  comments_error: 'Error posting comment',
  comments_anonymous: 'Anonymous',
  comments_latest: 'Latest comments',
  comments_on_product: 'on product',
  comments_on_market: 'on market',
  comments_on_insumo: 'on input',

  // Settings - comments & account
  settings_comments: 'Comments',
  settings_comments_desc: 'Enable or disable the comments section in the app.',
  settings_comments_toggle: 'Show comments',
  settings_account: 'Account',
  settings_account_desc: 'Sign in to leave comments.',
  settings_sign_in: 'Sign in',

  // Search
  search_placeholder: 'Search...',
};

const translations: Record<Locale, Translations> = { es, en };

export function getTranslations(locale: Locale): Translations {
  return translations[locale];
}
