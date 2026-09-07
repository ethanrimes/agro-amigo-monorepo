# Demo verification

## Data checks

Azure PostgreSQL checks passed for all current price, coffee, TRM, input and daily observations: no rows outside the rolling Colombia-date interval and no missing document IDs. The first full integrity pass recomputed SHA-256 for 407 archived files (193,100,399 bytes); the subsequent FEPCafé benchmark adds one intact original PDF, whose SHA-256 was checked separately (408 total documents).

Counts at the demo snapshot: 1,122 municipalities; 18,358 municipal crop references; 1,556 calendars; 62,181 suitability classifications; 1,038 soil summaries; 20,522 complete market-years; 22 cost templates; 10,070 recent input-price observations; 425 daily quotes; two dated reference/monitoring notices. No fabricated private buyer offers.

Independent source checks reconciled potato (page 2), bean Huila (page 13) and tomato Huila (page 10) template totals/yields; the daily Habichuela/Montería quote matched COP 6,250 in the DANE bulletin. Date-trigger rejection, repeat-import counts and blocked application price writes passed. Representative generated PDF pages and original cost/reference pages were rendered and inspected visually.

## Application checks

The 28-test browser suite passed locally on desktop and mobile against the Azure database. The deployed suite passed 27/28 initially; one navigation failed with host `ERR_NETWORK_CHANGED` during emulator startup and passed on the targeted rerun. The final PDF compatibility build passed four targeted desktop/mobile source-viewer tests and the Android test on Android 15 / WebView 124. The native test verified live data, PDF page rendering, Android DownloadManager, native back, offer arithmetic and device persistence. The system document picker also saved a budget JSON with the expected COP 600,000 total, three scenarios and source identifiers; the downloaded PDF hash matched its Azure document ID.

Tests cover profile persistence, live seven-day weather, weather failure states, crop references, seasonal minimum-history behavior, cost arithmetic and commission, saved scenario provenance, accepted quote quantities, kg/load conversions, expiry, buyer landed cost, input units, daily data, PDF pagination and byte integrity. They also check horizontal overflow and capture screenshots.

The production Next.js build and Android APK/lint checks passed. `npm audit` reported zero vulnerabilities. The ZIP excludes dotenv files, and a client-asset scan found no database credentials. Deployment compares a unique release artifact and confirms PostgreSQL health. The published APK's SHA-256 matches the locally built APK.

Screenshots and Playwright reports are generated under `artifacts` and `apps/web/playwright-report`, excluded from Git. Runtime/source limitations are in DATA_SOURCES.md; these checks do not validate agronomic prediction accuracy or commercial buyer reliability.

## iOS restoration and richer shared design

The active Flutter client is under `apps/ios`, with the existing native bundle identifier and TestFlight workflow retained. Flutter analysis, the origin-policy test, the iOS 18+ unsigned release build and GitHub Actions workflow validation pass. The existing GitHub run history confirms that the native workflow previously completed its TestFlight release job. Local verification was completed before GitHub delivery; the release workflow reports signing and upload status.

The richer shared interface passed the existing 28 desktop/mobile browser checks. Four targeted PDF checks passed locally after replacing PDF.js text extraction with explicit stream readers for older WebKit. The added compatibility check passed against the live Azure app on desktop and mobile; one mobile navigation initially hit a connection reset and passed on the targeted rerun. The iOS simulator verified real prices, Pitalito profile persistence, the FEPCafé PDF on page 6 (including its COP 1,550,805 text), native back navigation and the JSON share sheet. Export cancellation is checked to leave neither a connection error nor a running loading bar. Screenshots are `artifacts/ios-evidence.png`, `artifacts/ios-export.png` and `artifacts/rich-*.png`.

The final Azure release and database health were checked. Native signing and a new TestFlight upload still depend on running the preserved release workflow with the existing GitHub credentials.

## iPhone layout and simpler styling

The iPhone 17 Pro simulator verified a 402 × 812-point WebView below the 62-point top safe area, reaching the 874-point screen bottom. Its five tabs were approximately 80.4 points wide, with 34 points of padding for the home indicator. Navigating between home, saved products and prices preserved the WebView frame. The native suite also passed profile persistence, the archived FEPCafé PDF on page 6, page back navigation and native JSON sharing.

The existing 30 desktop/mobile browser checks passed. Ten additional Chromium/WebKit checks cover 375 × 667, 390 × 844, 430 × 932 and 932 × 430 viewports, parent-route tab selection, equal touch targets, full page width/height and larger phone text. Test setup was corrected to select a municipality before editing the farm name, using the department's published uppercase value and its accessible combobox role; both text-size checks then passed. The production build and Flutter analysis passed. Screenshots are `artifacts/ios-layout-*.png`, `artifacts/layout-*.png` and `artifacts/basic-*-iphone.png`.

The revised web release was deployed to Azure and its artifact ID and database health verified. Native geometry checks wait for the stylesheet before measuring, avoiding transient unstyled HTML during first load. The simpler design uses system fonts; unused custom font files were removed.
