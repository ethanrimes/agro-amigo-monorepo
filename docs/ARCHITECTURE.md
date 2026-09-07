# Application and data architecture

The active product has a Next.js web app, an Android client and a Flutter iOS client using the same Azure origin. No Supabase dependency remains. Both mobile clients add native navigation, document downloads/sharing, JSON export and connection recovery without duplicating product logic. The iOS client retains the existing TestFlight app identity and uses WKWebView.

## User journeys

- **Home:** choose the decision to make; farmer/purchaser role changes selling and buying language.
- **Mi finca:** municipality, crop/system, area, stage, irrigation and optional dates/coordinates/altitude, saved locally. A clearly labeled Pitalito example is available.
- **Weekly plan:** seven-day Open-Meteo forecast, transparent weather-triggered work suggestions, locally dismissible tasks and dated official monitoring/reference publications.
- **Explore crops:** municipal EVA production/yield, compatible SIPRA crop/semester classifications, regional laboratory soil context and a route into the budget.
- **Budget:** editable area, saleable yield, losses, costs/timing, wholesale-to-farm discount, sale costs and commission. Producing-year/establishment/cycle periods remain distinct. Lower/central/upper scenarios, break-even price, preharvest cash allocation, historical calendars and harvest-date calculations. Save/export assumptions and document identifiers.
- **Offers:** privately compare two or three quotes, accepted quantity, price units, deductions, costs, payment delay and expiry. Farmer net receipt and buyer landed cost are separate calculations. No fabricated buyers or published quotes.
- **Prices:** monthly product history and market comparisons; a separate daily bulletin retains its own product/market definitions. Coffee has daily national FNC reference, factor adjustments, regional delivery prices and TRM.
- **Sources:** immutable documents, a searchable library, exact PDF-page/dataset links, publisher URL, reference period, retrieval time and SHA-256 integrity identifier.

## Server boundary

`apps/web/src/lib/server` is server-only. PostgreSQL connections use certificate validation, a small pooled connection limit and statement timeout. Parameterized API queries validate/limit inputs and return plain Spanish errors without SQL or connection details. The application role can SELECT reference tables and INSERT public weather snapshots; it cannot modify official data or documents.

`source_document` holds original PDF/XLSX/JSON/text bytes. `document_alias` points to a current version, while observation records and saved scenarios link to immutable hashes. DANE's original price source is XLSX: generated PDFs explicitly identify themselves as AgroAmigo extracts and retain workbook/sheet/row locators plus links to the original workbook. Original official PDFs are archived intact. PDF.js renders locally inside the app with bundled worker/fonts; non-PDF source data can show relevant records and preserve a downloadable original.

`price_observation`, coffee, TRM, input and daily data are guarded by Colombia-date rolling windows. `seasonal_year` is separate and holds five complete prior years. Crop reference data is not represented as a current observation. Prices are nominal. No interpolation fills missing source rows.

## Local data

Farm profiles, saved products, quotes, task status and up to six scenarios are stored on the user's device. They are not uploaded or published. Climate requests send rounded coordinates (0.01°) to the server/provider and store the public forecast response for provenance. Municipal default points are explicitly distinguished from a farm location. User-entered dates and yields are assumptions or records, not remotely verified facts.

## Refresh and deployment

Official prices/references are a dated demonstration snapshot; climate is fetched on use. Run the documented import sequence when refreshing snapshots, then verify document integrity and data boundaries. Deployment bundles the standalone server, static assets, PDF worker assets and APK. It excludes dotenv credentials and verifies both an artifact-specific release ID and the database health endpoint.

GitHub Actions builds web, Android and iOS, checks Python syntax, runs Android lint and checks iOS navigation rules. The retained `agroamigo-iphone-build.yml` workflow runs on every push/PR; successful builds on `main` automatically sign and upload to TestFlight using the existing native-app secrets. Other branches and pull requests only build. Web deployment remains a separate Azure operation. End-to-end browser tests need the configured Azure database or `PLAYWRIGHT_BASE_URL`; iOS integration tests use the live Azure demo in a simulator.

## Cleanup record

The active Flutter iOS client was moved from `agroamigo-iphone` to `apps/ios`, its old Supabase screens were replaced with the shared Azure interface, and its existing successful TestFlight workflow was retained with updated paths. The old Expo/React Native and second Next web prototypes, Expo release workflow and unused shared Supabase package were removed. Twenty unreachable components, providers, translation/map modules and Supabase initializers were removed from the active web app. Legacy Supabase migrations, one-off repair scripts and its ingestion stack were replaced by the independent Azure importers. Source municipal files were preserved; old implementations remain available in Git history.

## Shared visual design

`apps/web/src/app/globals.css` provides component layout and responsive behavior; `field-theme.css` defines the shared colors, photographic headers, crop cards, alert treatments and mobile refinements. All three clients load this same product interface. The iOS deployment target is iOS 18, matching the supported PDF viewer browser baseline. PDF text uses explicit stream readers for older WebKit versions without asynchronous stream iteration.

Typography uses standard platform fonts without downloaded display fonts. Solid fills, visible borders, larger labels and simple corners keep the interface familiar. The five mobile destinations share equal grid columns and the same parent-route selection rules as desktop navigation. Short pages fill the dynamic viewport; landscape phones retain mobile navigation.

The iOS WebView fills a Stack below the top safe area and extends to the bottom screen edge. Loading is an overlay and there is no separate native back-button row to change the page height after navigation. The web viewport uses `viewport-fit=cover`; the tab bar adds `env(safe-area-inset-bottom)` so its background reaches the edge while controls clear the home indicator. This follows [WebKit's safe-area guidance](https://webkit.org/blog/7929/designing-websites-for-iphone-x/). Page back buttons and native swipe gestures remain available.
