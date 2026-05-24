// Auto-port of `agroamigo-app/src/translations/index.ts`.
// All keys preserved 1:1 so screens can index by the same names.

enum AppLocale { es, en }

class Translations {
  // Navigation
  final String nav_home;
  final String nav_home_tab;
  final String nav_products;
  final String nav_markets;
  final String nav_inputs;
  final String nav_map;
  final String nav_settings;
  final String nav_product;
  final String nav_market;
  final String nav_input;

  // Settings
  final String settings_default_market;
  final String settings_default_market_desc;
  final String settings_national_avg;
  final String settings_department;
  final String settings_city;
  final String settings_specific_market;
  final String settings_select_option;
  final String settings_no_results;
  final String settings_showing_n_of;
  final String settings_search_placeholder;
  final String settings_search_min_chars;
  final String settings_font_size;
  final String settings_font_size_desc;
  final String settings_font_small;
  final String settings_font_normal;
  final String settings_font_large;
  final String settings_font_xlarge;
  final String settings_preview;
  final String settings_preview_desc;
  final String settings_language;
  final String settings_language_desc;
  final String settings_charts;
  final String settings_charts_desc;
  final String settings_chart_avg_line;
  final String settings_chart_trend_line;
  final String settings_chart_min_max_callouts;
  final String settings_chart_interactive;

  // Product detail – extra
  final String product_vs_prev_week;
  final String product_national_avg;
  final String product_daily_avg;
  final String product_total_sum;
  final String product_pct_total;
  final String product_sort_asc;
  final String product_sort_desc;
  final String product_median;
  final String product_mean;

  // Home
  final String home_loading;
  final String home_watchlist;
  final String home_no_recent_data;
  final String home_categories;
  final String home_top_increases;
  final String home_top_decreases;
  final String home_top_supply;
  final String home_last_week;
  final String home_last_7_days;
  final String home_help_methodology;
  final String home_market_info_title;
  final String home_market_info_text;
  final String home_market_info_change;
  final String home_market_info_blurb_nacional;
  final String home_market_info_blurb_departamento;
  final String home_market_info_blurb_ciudad;
  final String home_market_info_blurb_mercado;
  final String home_market_legend_selected;
  final String home_market_legend_fallback;
  final String home_understood;
  final String common_view_all;
  final String common_close;
  final String map_view_details;
  final String supply_hint_market_provenance;
  final String supply_hint_origin_only;
  final String supply_hint_product_destinations;
  final String supply_hint_origin_markets;
  final String attribution_photo_by;
  final String home_help;
  final String home_app_guide;
  final String home_help_home_text;
  final String home_help_products_text;
  final String home_help_markets_text;
  final String home_help_inputs_text;
  final String home_help_map_text;
  final String home_sources_methodology;
  final String home_sources_text;
  final String home_disclaimer;

  // Products page
  final String products_search;
  final String products_all;
  final String products_not_found;

  // Insumos page
  final String inputs_search;
  final String inputs_all;
  final String inputs_not_found;

  // Markets page
  final String markets_search;
  final String markets_not_found;

  // Product detail
  final String product_not_found;
  final String product_price_section;
  final String product_prices;
  final String product_filters;
  final String product_all_markets;
  final String product_all_presentations;
  final String product_min;
  final String product_avg;
  final String product_max;
  final String product_no_price_data;
  final String product_prices_by_market;
  final String product_prices_by_market_note;
  final String product_market_fallback;
  final String product_supply_section;
  final String product_supply;
  final String product_total;
  final String product_no_supply_data;
  final String product_provenance;
  final String product_provenance_subtitle;
  final String product_unknown;
  final String product_price_at;

  // Time ranges
  final String time_1w;
  final String time_1m;
  final String time_3m;
  final String time_6m;
  final String time_1y;
  final String time_all;

  // Insumo detail
  final String input_not_found;
  final String input_departments;
  final String input_municipalities;
  final String input_department_count;
  final String input_municipality_count;
  final String input_price_history;
  final String input_price_by_dept;
  final String input_no_data;
  final String input_unknown;
  final String input_price_detail;
  final String input_presentation;

  // Market detail
  final String market_not_found;
  final String market_products;
  final String market_categories;
  final String market_recent_products;
  final String market_prices_at;
  final String market_no_recent_data;
  final String market_product_fallback;

  // Map
  final String map_prices;
  final String map_supply;
  final String map_loading;
  final String map_price_legend;
  final String map_supply_legend;
  final String map_no_data;
  final String map_source;
  final String map_select_product;
  final String map_search_product;
  final String map_all_products;
  final String map_no_highlight_note;
  final String map_pick_product_prompt;

  // Market comparator
  final String compare_prices_title;
  final String compare_supply_title;
  final String compare_national_avg;
  final String compare_all_markets;
  final String compare_search_market;
  final String compare_select_market;
  final String compare_product;
  final String compare_diff;
  final String compare_no_match;
  final String compare_no_results;
  final String compare_matching;
  final String compare_overall_avg;
  final String compare_loading;
  final String compare_observed;

  // Auth
  final String auth_sign_in;
  final String auth_sign_up;
  final String auth_sign_out;
  final String auth_create_account;
  final String auth_sign_in_desc;
  final String auth_create_account_desc;
  final String auth_username;
  final String auth_email;
  final String auth_password;
  final String auth_fill_all_fields;
  final String auth_username_too_short;
  final String auth_username_taken;
  final String auth_signup_success;
  final String auth_error;
  final String auth_account;
  final String auth_member_since;
  final String auth_go_back;
  final String auth_signed_in_as;

  // Comments
  final String comments_title;
  final String comments_placeholder;
  final String comments_sign_in_to_comment;
  final String comments_loading;
  final String comments_empty;
  final String comments_error;
  final String comments_anonymous;
  final String comments_latest;
  final String comments_on;
  final String comments_on_product;
  final String comments_on_market;
  final String comments_on_insumo;

  // Settings – comments & account
  final String settings_comments;
  final String settings_comments_desc;
  final String settings_comments_toggle;
  final String settings_account;
  final String settings_account_desc;
  final String settings_sign_in;

  // Search
  final String search_placeholder;

  const Translations({
    required this.nav_home,
    required this.nav_home_tab,
    required this.nav_products,
    required this.nav_markets,
    required this.nav_inputs,
    required this.nav_map,
    required this.nav_settings,
    required this.nav_product,
    required this.nav_market,
    required this.nav_input,
    required this.settings_default_market,
    required this.settings_default_market_desc,
    required this.settings_national_avg,
    required this.settings_department,
    required this.settings_city,
    required this.settings_specific_market,
    required this.settings_select_option,
    required this.settings_no_results,
    required this.settings_showing_n_of,
    required this.settings_search_placeholder,
    required this.settings_search_min_chars,
    required this.settings_font_size,
    required this.settings_font_size_desc,
    required this.settings_font_small,
    required this.settings_font_normal,
    required this.settings_font_large,
    required this.settings_font_xlarge,
    required this.settings_preview,
    required this.settings_preview_desc,
    required this.settings_language,
    required this.settings_language_desc,
    required this.settings_charts,
    required this.settings_charts_desc,
    required this.settings_chart_avg_line,
    required this.settings_chart_trend_line,
    required this.settings_chart_min_max_callouts,
    required this.settings_chart_interactive,
    required this.product_vs_prev_week,
    required this.product_national_avg,
    required this.product_daily_avg,
    required this.product_total_sum,
    required this.product_pct_total,
    required this.product_sort_asc,
    required this.product_sort_desc,
    required this.product_median,
    required this.product_mean,
    required this.home_loading,
    required this.home_watchlist,
    required this.home_no_recent_data,
    required this.home_categories,
    required this.home_top_increases,
    required this.home_top_decreases,
    required this.home_top_supply,
    required this.home_last_week,
    required this.home_last_7_days,
    required this.home_help_methodology,
    required this.home_market_info_title,
    required this.home_market_info_text,
    required this.home_market_info_change,
    required this.home_market_info_blurb_nacional,
    required this.home_market_info_blurb_departamento,
    required this.home_market_info_blurb_ciudad,
    required this.home_market_info_blurb_mercado,
    required this.home_market_legend_selected,
    required this.home_market_legend_fallback,
    required this.home_understood,
    required this.common_view_all,
    required this.common_close,
    required this.map_view_details,
    required this.supply_hint_market_provenance,
    required this.supply_hint_origin_only,
    required this.supply_hint_product_destinations,
    required this.supply_hint_origin_markets,
    required this.attribution_photo_by,
    required this.home_help,
    required this.home_app_guide,
    required this.home_help_home_text,
    required this.home_help_products_text,
    required this.home_help_markets_text,
    required this.home_help_inputs_text,
    required this.home_help_map_text,
    required this.home_sources_methodology,
    required this.home_sources_text,
    required this.home_disclaimer,
    required this.products_search,
    required this.products_all,
    required this.products_not_found,
    required this.inputs_search,
    required this.inputs_all,
    required this.inputs_not_found,
    required this.markets_search,
    required this.markets_not_found,
    required this.product_not_found,
    required this.product_price_section,
    required this.product_prices,
    required this.product_filters,
    required this.product_all_markets,
    required this.product_all_presentations,
    required this.product_min,
    required this.product_avg,
    required this.product_max,
    required this.product_no_price_data,
    required this.product_prices_by_market,
    required this.product_prices_by_market_note,
    required this.product_market_fallback,
    required this.product_supply_section,
    required this.product_supply,
    required this.product_total,
    required this.product_no_supply_data,
    required this.product_provenance,
    required this.product_provenance_subtitle,
    required this.product_unknown,
    required this.product_price_at,
    required this.time_1w,
    required this.time_1m,
    required this.time_3m,
    required this.time_6m,
    required this.time_1y,
    required this.time_all,
    required this.input_not_found,
    required this.input_departments,
    required this.input_municipalities,
    required this.input_department_count,
    required this.input_municipality_count,
    required this.input_price_history,
    required this.input_price_by_dept,
    required this.input_no_data,
    required this.input_unknown,
    required this.input_price_detail,
    required this.input_presentation,
    required this.market_not_found,
    required this.market_products,
    required this.market_categories,
    required this.market_recent_products,
    required this.market_prices_at,
    required this.market_no_recent_data,
    required this.market_product_fallback,
    required this.map_prices,
    required this.map_supply,
    required this.map_loading,
    required this.map_price_legend,
    required this.map_supply_legend,
    required this.map_no_data,
    required this.map_source,
    required this.map_select_product,
    required this.map_search_product,
    required this.map_all_products,
    required this.map_no_highlight_note,
    required this.map_pick_product_prompt,
    required this.compare_prices_title,
    required this.compare_supply_title,
    required this.compare_national_avg,
    required this.compare_all_markets,
    required this.compare_search_market,
    required this.compare_select_market,
    required this.compare_product,
    required this.compare_diff,
    required this.compare_no_match,
    required this.compare_no_results,
    required this.compare_matching,
    required this.compare_overall_avg,
    required this.compare_loading,
    required this.compare_observed,
    required this.auth_sign_in,
    required this.auth_sign_up,
    required this.auth_sign_out,
    required this.auth_create_account,
    required this.auth_sign_in_desc,
    required this.auth_create_account_desc,
    required this.auth_username,
    required this.auth_email,
    required this.auth_password,
    required this.auth_fill_all_fields,
    required this.auth_username_too_short,
    required this.auth_username_taken,
    required this.auth_signup_success,
    required this.auth_error,
    required this.auth_account,
    required this.auth_member_since,
    required this.auth_go_back,
    required this.auth_signed_in_as,
    required this.comments_title,
    required this.comments_placeholder,
    required this.comments_sign_in_to_comment,
    required this.comments_loading,
    required this.comments_empty,
    required this.comments_error,
    required this.comments_anonymous,
    required this.comments_latest,
    required this.comments_on,
    required this.comments_on_product,
    required this.comments_on_market,
    required this.comments_on_insumo,
    required this.settings_comments,
    required this.settings_comments_desc,
    required this.settings_comments_toggle,
    required this.settings_account,
    required this.settings_account_desc,
    required this.settings_sign_in,
    required this.search_placeholder,
  });
}

const Translations es = Translations(
  nav_home: 'AgroAmigo',
  nav_home_tab: 'Inicio',
  nav_products: 'Productos',
  nav_markets: 'Mercados',
  nav_inputs: 'Insumos',
  nav_map: 'Mapa',
  nav_settings: 'Configuración',
  nav_product: 'Producto',
  nav_market: 'Mercado',
  nav_input: 'Insumo',
  settings_default_market: 'Mercado predeterminado',
  settings_default_market_desc: 'Define qué precios se muestran en la pantalla de inicio.',
  settings_national_avg: 'Promedio nacional',
  settings_department: 'Departamento',
  settings_city: 'Ciudad',
  settings_specific_market: 'Mercado específico',
  settings_select_option: 'Selecciona una opción',
  settings_no_results: 'Sin resultados',
  settings_showing_n_of: 'Mostrando 50 de',
  settings_search_placeholder: 'Buscar',
  settings_search_min_chars: 'Escribe al menos 2 caracteres para buscar.',
  settings_font_size: 'Tamaño de texto',
  settings_font_size_desc: 'Ajusta el tamaño de la tipografía.',
  settings_font_small: 'Pequeño',
  settings_font_normal: 'Normal',
  settings_font_large: 'Grande',
  settings_font_xlarge: 'Muy grande',
  settings_preview: 'Vista previa',
  settings_preview_desc: 'Así se verá el texto con el tamaño seleccionado.',
  settings_language: 'Idioma',
  settings_language_desc: 'Cambia el idioma de la aplicación.',
  settings_charts: 'Gráficos',
  settings_charts_desc: 'Configura las opciones de los gráficos de línea.',
  settings_chart_avg_line: 'Línea promedio',
  settings_chart_trend_line: 'Línea de tendencia',
  settings_chart_min_max_callouts: 'Anotaciones mín/máx',
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
  home_loading: 'Cargando datos...',
  home_watchlist: 'Seguimiento',
  home_no_recent_data: 'Sin datos recientes',
  home_categories: 'Categorías',
  home_top_increases: 'Mayores alzas',
  home_top_decreases: 'Mayores bajas',
  home_top_supply: 'Mayor abastecimiento',
  home_last_week: 'Última semana',
  home_last_7_days: 'Últimos 7 días',
  home_help_methodology: 'Ayuda y metodología',
  home_market_info_title: 'Mercado predeterminado',
  home_market_info_text: 'Los precios que ves en la pantalla de inicio provienen de tu mercado predeterminado:',
  home_market_info_change: 'Puedes cambiar tu mercado en',
  home_market_info_blurb_nacional: 'Actualmente estás viendo promedios nacionales. Los precios reflejan el comportamiento general del mercado colombiano.',
  home_market_info_blurb_departamento: 'Estás viendo precios promedio del departamento seleccionado.',
  home_market_info_blurb_ciudad: 'Estás viendo precios promedio de la ciudad seleccionada.',
  home_market_info_blurb_mercado: 'Estás viendo precios de un mercado específico. Los datos corresponden directamente a las cotizaciones reportadas.',
  home_market_legend_selected: 'Precio del mercado seleccionado',
  home_market_legend_fallback: 'Promedio nacional (cuando no hay datos locales)',
  home_understood: 'Entendido',
  common_view_all: 'Ver todo',
  common_close: 'Cerrar',
  map_view_details: 'Ver detalles',
  supply_hint_market_provenance: 'Toca para ver procedencia.',
  supply_hint_origin_only: 'Toca para ver solo este origen.',
  supply_hint_product_destinations: 'Toca para ver la procedencia de ese mercado.',
  supply_hint_origin_markets: 'Toca para ver los mercados que reciben de ese origen.',
  attribution_photo_by: 'Foto',
  home_help: 'Ayuda',
  home_app_guide: 'Guía de la aplicación',
  home_help_home_text: 'Tu panel principal con seguimiento, categorías y movimientos del mercado.',
  home_help_products_text: 'Más de 700 productos con precios históricos y comparación entre mercados.',
  home_help_markets_text: '43 mercados mayoristas y 500+ mercados municipales.',
  home_help_inputs_text: 'Precios de 2,000+ insumos agropecuarios por departamento.',
  home_help_map_text: 'Visualiza precios y flujos de abastecimiento sobre el mapa de Colombia.',
  home_sources_methodology: 'Fuentes y metodología',
  home_sources_text: 'Todos los datos provienen del SIPSA (Sistema de Información de Precios y Abastecimiento del Sector Agropecuario), operado por el DANE de Colombia.',
  home_disclaimer: 'Esta aplicación no es un producto oficial del DANE.',
  products_search: 'Buscar producto...',
  products_all: 'Todos',
  products_not_found: 'No se encontraron productos',
  inputs_search: 'Buscar insumo...',
  inputs_all: 'Todos',
  inputs_not_found: 'No se encontraron insumos',
  markets_search: 'Buscar mercado o ciudad...',
  markets_not_found: 'No se encontraron mercados',
  product_not_found: 'Producto no encontrado',
  product_price_section: 'Precios',
  product_prices: 'Precios',
  product_filters: 'Filtros',
  product_all_markets: 'Todos',
  product_all_presentations: 'Todas',
  product_min: 'Mín',
  product_avg: 'Prom',
  product_max: 'Máx',
  product_no_price_data: 'Sin datos de precios para este período',
  product_prices_by_market: 'Precios por mercado',
  product_prices_by_market_note: 'Precios más recientes de cada mercado.',
  product_market_fallback: 'Mercado',
  product_supply_section: 'Abastecimiento',
  product_supply: 'Abastecimiento',
  product_total: 'Total',
  product_no_supply_data: 'Sin datos de abastecimiento',
  product_provenance: 'Procedencia',
  product_provenance_subtitle: 'Departamentos de origen',
  product_unknown: 'Desconocido',
  product_price_at: 'Precio al',
  time_1w: '1S',
  time_1m: '1M',
  time_3m: '3M',
  time_6m: '6M',
  time_1y: '1A',
  time_all: 'Todo',
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
  input_presentation: 'Presentación',
  market_not_found: 'Mercado no encontrado',
  market_products: 'Productos',
  market_categories: 'Categorías',
  market_recent_products: 'Productos recientes',
  market_prices_at: 'Precios al',
  market_no_recent_data: 'Sin datos recientes',
  market_product_fallback: 'Producto',
  map_prices: 'Precios',
  map_supply: 'Abastecimiento',
  map_loading: 'Cargando mapa...',
  map_price_legend: 'Precio promedio por departamento (30 días)',
  map_supply_legend: 'Volumen de abastecimiento por departamento (30 días)',
  map_no_data: 'Sin datos',
  map_source: 'Fuente: SIPSA-DANE',
  map_select_product: 'Seleccionar producto',
  map_search_product: 'Buscar producto...',
  map_all_products: 'Todos los productos',
  map_no_highlight_note: 'Si no se resaltan departamentos o mercados, no hay datos para este producto en los últimos 30 días.',
  map_pick_product_prompt: 'Selecciona un producto para ver el mapa por departamento.',
  compare_prices_title: 'Comparar precios',
  compare_supply_title: 'Comparar abastecimiento',
  compare_national_avg: 'Promedio nacional',
  compare_all_markets: 'Promedio de todos los mercados',
  compare_search_market: 'Buscar mercado...',
  compare_select_market: 'Selecciona un mercado para comparar',
  compare_product: 'Producto',
  compare_diff: 'Dif',
  compare_no_match: 'No se encontraron productos en común',
  compare_no_results: 'No se encontraron mercados',
  compare_matching: 'productos en común',
  compare_overall_avg: 'Promedio general',
  compare_loading: 'Cargando comparación...',
  compare_observed: 'Observado el',
  auth_sign_in: 'Iniciar sesión',
  auth_sign_up: 'Crear cuenta',
  auth_sign_out: 'Cerrar sesión',
  auth_create_account: 'Crear cuenta',
  auth_sign_in_desc: 'Inicia sesión para dejar comentarios.',
  auth_create_account_desc: 'Crea una cuenta para participar en la comunidad.',
  auth_username: 'Nombre de usuario',
  auth_email: 'Correo electrónico',
  auth_password: 'Contraseña',
  auth_fill_all_fields: 'Completa todos los campos',
  auth_username_too_short: 'El nombre de usuario debe tener al menos 3 caracteres',
  auth_username_taken: 'Este nombre de usuario ya está en uso',
  auth_signup_success: 'Cuenta creada. Revisa tu correo para confirmar.',
  auth_error: 'Error de autenticación',
  auth_account: 'Mi cuenta',
  auth_member_since: 'Miembro desde',
  auth_go_back: 'Volver',
  auth_signed_in_as: 'Conectado como',
  comments_title: 'Comentarios',
  comments_placeholder: 'Escribe un comentario...',
  comments_sign_in_to_comment: 'Inicia sesión para comentar',
  comments_loading: 'Cargando comentarios...',
  comments_empty: 'Aún no hay comentarios. Sé el primero.',
  comments_error: 'Error al publicar comentario',
  comments_anonymous: 'Anónimo',
  comments_latest: 'Últimos comentarios',
  comments_on: 'en',
  comments_on_product: 'en producto',
  comments_on_market: 'en mercado',
  comments_on_insumo: 'en insumo',
  settings_comments: 'Comentarios',
  settings_comments_desc: 'Activa o desactiva la sección de comentarios en la aplicación.',
  settings_comments_toggle: 'Mostrar comentarios',
  settings_account: 'Cuenta',
  settings_account_desc: 'Inicia sesión para dejar comentarios.',
  settings_sign_in: 'Iniciar sesión',
  search_placeholder: 'Buscar...',
);

const Translations en = Translations(
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
  settings_search_min_chars: 'Type at least 2 characters to search.',
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
  home_market_info_blurb_nacional: 'You are currently viewing national averages. The prices reflect the general behavior of the Colombian market.',
  home_market_info_blurb_departamento: 'You are viewing average prices for the selected department.',
  home_market_info_blurb_ciudad: 'You are viewing average prices for the selected city.',
  home_market_info_blurb_mercado: 'You are viewing prices from a specific market. The data corresponds directly to the reported quotations.',
  home_market_legend_selected: 'Price from the selected market',
  home_market_legend_fallback: 'National average (when no local data is available)',
  home_understood: 'Got it',
  common_view_all: 'See all',
  common_close: 'Close',
  map_view_details: 'View details',
  supply_hint_market_provenance: 'Tap to see provenance.',
  supply_hint_origin_only: 'Tap to filter to this origin.',
  supply_hint_product_destinations: 'Tap to see provenance for that market.',
  supply_hint_origin_markets: 'Tap to see the markets that receive from that origin.',
  attribution_photo_by: 'Photo',
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
  products_search: 'Search product...',
  products_all: 'All',
  products_not_found: 'No products found',
  inputs_search: 'Search input...',
  inputs_all: 'All',
  inputs_not_found: 'No inputs found',
  markets_search: 'Search market or city...',
  markets_not_found: 'No markets found',
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
  time_1w: '1W',
  time_1m: '1M',
  time_3m: '3M',
  time_6m: '6M',
  time_1y: '1Y',
  time_all: 'All',
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
  market_not_found: 'Market not found',
  market_products: 'Products',
  market_categories: 'Categories',
  market_recent_products: 'Recent products',
  market_prices_at: 'Prices as of',
  market_no_recent_data: 'No recent data',
  market_product_fallback: 'Product',
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
  map_pick_product_prompt: 'Pick a product to see the department map.',
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
  compare_observed: 'Observed on',
  auth_sign_in: 'Sign in',
  auth_sign_up: 'Sign up',
  auth_sign_out: 'Sign out',
  auth_create_account: 'Create account',
  auth_sign_in_desc: 'Sign in to post comments.',
  auth_create_account_desc: 'Create an account to join the community.',
  auth_username: 'Username',
  auth_email: 'Email',
  auth_password: 'Password',
  auth_fill_all_fields: 'Fill all fields',
  auth_username_too_short: 'Username must be at least 3 characters',
  auth_username_taken: 'This username is already taken',
  auth_signup_success: 'Account created. Check your email to confirm.',
  auth_error: 'Authentication error',
  auth_account: 'My account',
  auth_member_since: 'Member since',
  auth_go_back: 'Back',
  auth_signed_in_as: 'Signed in as',
  comments_title: 'Comments',
  comments_placeholder: 'Write a comment...',
  comments_sign_in_to_comment: 'Sign in to comment',
  comments_loading: 'Loading comments...',
  comments_empty: 'No comments yet. Be the first.',
  comments_error: 'Error posting comment',
  comments_anonymous: 'Anonymous',
  comments_latest: 'Latest comments',
  comments_on: 'on',
  comments_on_product: 'on product',
  comments_on_market: 'on market',
  comments_on_insumo: 'on input',
  settings_comments: 'Comments',
  settings_comments_desc: 'Enable or disable the comments section in the app.',
  settings_comments_toggle: 'Show comments',
  settings_account: 'Account',
  settings_account_desc: 'Sign in to post comments.',
  settings_sign_in: 'Sign in',
  search_placeholder: 'Search...',
);

Translations getTranslations(AppLocale locale) {
  switch (locale) {
    case AppLocale.en:
      return en;
    case AppLocale.es:
      return es;
  }
}
