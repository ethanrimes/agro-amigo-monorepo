/* Real Android WebView regression checks against the deployed Azure app.
 * Requires the installed debuggable app and an explicit emulator serial.
 * ANDROID_TEST_CASES is an optional regular expression for a focused rerun.
 * ANDROID_TEST_SUITE=baseline runs existing functionality before deployment.
 */
const { _android, expect: baseExpect } = require("@playwright/test");
const { mkdirSync, writeFileSync, existsSync, unlinkSync } = require("node:fs");
const { execFileSync } = require("node:child_process");
const { createHash } = require("node:crypto");
const expect = baseExpect.configure({ timeout: 60000 });
const origin = "https://agroamigo-demo-9a04.azurewebsites.net";
const dir =
  process.env.ANDROID_TEST_ARTIFACTS || "artifacts/android-validation-new";
const selection = process.env.ANDROID_TEST_CASES
  ? new RegExp(process.env.ANDROID_TEST_CASES)
  : null;
const baseline = process.env.ANDROID_TEST_SUITE === "baseline";
const money = (n) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(Number(n));
const percent = (n) =>
  `${n > 0 ? "+" : ""}${Number(n).toLocaleString("es-CO", { maximumFractionDigits: 2 })} %`;
const numeric = (text) =>
  Number(text.replace(/[^\d,-]/g, "").replace(",", "."));
const fold = (s) =>
  s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
mkdirSync(dir, { recursive: true });
let activeDevice;

(async () => {
  const serial = process.env.ANDROID_TEST_SERIAL;
  if (!serial || !serial.startsWith("emulator-"))
    throw Error("Set ANDROID_TEST_SERIAL to the intended Android emulator");
  const adb = `${process.env.ANDROID_HOME || "/Users/ethan/Library/Android/sdk"}/platform-tools/adb`;
  const device = (await _android.devices()).find((d) => d.serial() === serial);
  if (!device) throw Error(`Emulator ${serial} is not connected`);
  activeDevice = device;
  device.setDefaultTimeout(60000);
  const shell = async (command) => String(await device.shell(command)).trim();
  const networkBefore = {
    wifi: await shell("settings get global wifi_on"),
    data: await shell("settings get global mobile_data"),
  };
  const native = {
    serial,
    model: await shell("getprop ro.product.model"),
    android: await shell("getprop ro.build.version.release"),
    sdk: await shell("getprop ro.build.version.sdk"),
    resolution: await shell("wm size"),
    package: "co.agroamigo.demo",
    webview: await shell("dumpsys webviewupdate"),
  };
  await device.shell("am start -n co.agroamigo.demo/.MainActivity");
  let page = await (await device.webView({ pkg: "co.agroamigo.demo" })).page();
  page.setDefaultTimeout(60000);
  page.setDefaultNavigationTimeout(90000);
  const startedAt = new Date().toISOString();
  const errors = [],
    results = [],
    requests = [];
  let activeStep = "setup";
  const watchPage = (p) => {
    p.on("pageerror", (e) =>
      errors.push({ step: activeStep, message: e.message }),
    );
    p.on("response", (r) => {
      if (r.url().startsWith(origin + "/api/"))
        requests.push({
          step: activeStep,
          path: r.url().slice(origin.length),
          status: r.status(),
        });
    });
  };
  watchPage(page);
  await page.goto(origin, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".product-card").first()).toBeVisible();
  const readRelease = () =>
    page.evaluate(async () => {
      const r = await fetch("/release.json", { cache: "no-store" });
      if (!r.ok) throw Error("Deployment release metadata unavailable");
      return r.json();
    });
  const webReleaseBefore = await readRelease();
  if (
    process.env.ANDROID_TEST_RELEASE &&
    webReleaseBefore.id !== process.env.ANDROID_TEST_RELEASE
  )
    throw Error("Unexpected web release: " + webReleaseBefore.id);
  const saved = await page.evaluate(() =>
    Object.fromEntries(Object.entries(localStorage)),
  );
  const snapshotPath = `${dir}/.restore-settings.private.json`;
  if (existsSync(snapshotPath))
    throw Error(
      "A previous private settings snapshot awaits restoration: " +
        snapshotPath,
    );
  writeFileSync(snapshotPath, JSON.stringify(saved), { mode: 0o600 });
  native.userAgent = await page.evaluate(() => navigator.userAgent);
  if (!native.userAgent.includes("AgroAmigoAndroid/1.0"))
    throw Error("Expected the installed Android app, not a browser emulation");
  const screenshot = (name) =>
    writeFileSync(
      `${dir}/${name}.png`,
      execFileSync(adb, ["-s", serial, "exec-out", "screencap", "-p"], {
        maxBuffer: 16 * 1024 * 1024,
      }),
    );
  const waitForNetwork = async () =>
    expect
      .poll(
        async () =>
          (await shell("dumpsys connectivity"))
            .split("\n")
            .some(
              (l) =>
                l.includes("NetworkAgentInfo{") && l.includes("IS_VALIDATED"),
            ),
        { timeout: 60000 },
      )
      .toBe(true);
  const captureElement = async (locator, name) => {
    await locator.evaluate((el) =>
      el.scrollIntoView({ block: "start", behavior: "instant" }),
    );
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    screenshot(name);
  };
  const get = async (path) =>
    page.evaluate(async (path) => {
      const r = await fetch(path, { signal: AbortSignal.timeout(120000) });
      if (!r.ok) throw Error(`${r.status} ${path}`);
      return r.json();
    }, path);
  const navigate = async (path) => {
    await page.goto(origin + path, { waitUntil: "domcontentloaded" });
  };
  const nativeDownload = async (id, extension) => {
    const expected = await page.evaluate(async (id) => {
      const response = await fetch("/api/evidence/" + id + "/content");
      if (!response.ok)
        throw Error("Original document is unavailable: " + response.status);
      const bytes = await response.arrayBuffer();
      return Array.from(
        new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
      )
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
    }, id);
    const before = new Set(
      (await shell("ls -1 /sdcard/Download")).split(/\r?\n/),
    );
    await page
      .getByRole("link", { name: "Descargar archivo", exact: true })
      .click();
    let matchingFile;
    await expect
      .poll(
        async () => {
          const files = (await shell("ls -1 /sdcard/Download"))
            .split(/\r?\n/)
            .filter(
              (f) =>
                !before.has(f) &&
                /^[a-zA-Z0-9_.-]+$/.test(f) &&
                f.endsWith("." + extension),
            );
          matchingFile = files.find(
            (file) =>
              createHash("sha256")
                .update(
                  execFileSync(
                    adb,
                    [
                      "-s",
                      serial,
                      "exec-out",
                      "cat",
                      "/sdcard/Download/" + file,
                    ],
                    { maxBuffer: 32 * 1024 * 1024 },
                  ),
                )
                .digest("hex") === expected,
          );
          return Boolean(matchingFile);
        },
        { timeout: 60000 },
      )
      .toBe(true);
    return {
      expectedSha256: expected,
      newNativeDownload: matchingFile,
      nativeDownloadBytesMatch: true,
    };
  };
  const layout = async () => {
    expect(
      await page.evaluate(() => ({
        width: innerWidth,
        content: document.documentElement.scrollWidth,
      })),
    ).toEqual(expect.objectContaining({ width: expect.any(Number) }));
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
  };
  const filters = (scope = page) => scope.locator(".applied-filters");
  const readableFilters = async (scope) => {
    const container = filters(scope);
    expect(
      await container.evaluate(
        (el) => el.clientHeight >= 44 && el.scrollHeight <= el.clientHeight + 1,
      ),
    ).toBe(true);
    expect(
      await container
        .locator(".filter-chip")
        .evaluateAll(
          (chips) =>
            chips.length > 0 &&
            chips.every(
              (chip) =>
                chip.getBoundingClientRect().height >= 28 &&
                chip.scrollHeight <= chip.clientHeight + 1,
            ),
        ),
    ).toBe(true);
  };
  const descending = async (selector) => {
    const values = (await page.locator(selector).allTextContents()).map(
      numeric,
    );
    expect(values.length).toBeGreaterThan(0);
    expect(
      values.every(
        (v, i) => Number.isFinite(v) && (i === 0 || values[i - 1] >= v),
      ),
    ).toBe(true);
    return values;
  };
  const option = async (select, match) => {
    await expect
      .poll(
        async () =>
          (await select.locator("option").allTextContents()).some((text) =>
            match.test(fold(text)),
          ),
        { message: "Required select option should load: " + match },
      )
      .toBe(true);
    const options = await select
      .locator("option")
      .evaluateAll((nodes) =>
        nodes.map((n) => ({ value: n.value, text: n.textContent })),
      );
    const chosen = options.find((o) => match.test(fold(o.text || "")));
    if (!chosen) throw Error("Required select option not found: " + match);
    await select.selectOption(chosen.value);
    return chosen;
  };
  let lemon, market, cityDocument, workbookDocument;
  async function fixtureProduct(
    id = "limon-tahiti",
    presentation = "Bulto",
    units = "24 Kilogramo",
  ) {
    const params = new URLSearchParams({
      series: "city",
      presentation,
      units,
      history: "all",
    });
    let all = await get(`/api/products/${id}?${params}`);
    const actualPresentation = all.options.presentations.find(
      (p) => fold(p) === fold(presentation),
    );
    if (!actualPresentation)
      throw Error(
        "Required native package presentation missing: " + presentation,
      );
    params.set("presentation", actualPresentation);
    if (actualPresentation !== presentation)
      all = await get(`/api/products/${id}?${params}`);
    const found = all.options.markets.find((m) =>
      fold(m.name).includes("barranquillita"),
    );
    expect(found).toBeTruthy();
    params.set("market", found.id);
    return {
      id,
      params,
      data: await get(`/api/products/${id}?${params}`),
      market: found,
    };
  }
  async function step(name, fn, isBaseline = false) {
    if ((selection && !selection.test(name)) || (baseline && !isBaseline))
      return;
    activeStep = name;
    const started = Date.now();
    console.log("START", name);
    try {
      const evidence = await fn();
      results.push({
        name,
        status: "passed",
        ms: Date.now() - started,
        ...(evidence ? { evidence } : {}),
      });
      console.log("PASS", name);
    } catch (e) {
      results.push({
        name,
        status: "failed",
        ms: Date.now() - started,
        error: String(e.stack || e).slice(0, 5000),
      });
      console.error("FAIL", name, e.message);
    }
    try {
      screenshot(name);
    } catch (e) {
      results.push({
        name: `${name}-screenshot`,
        status: "failed",
        error: e.message,
      });
    }
  }
  async function comparison(kind, params = "") {
    const data = await get(`/api/compare/${kind}?${params}`);
    const matches = data.rows.filter((r) => r.b);
    expect(matches.length).toBeGreaterThan(0);
    for (const row of matches) {
      expect(row.a.price).toBeGreaterThan(0);
      expect(row.percent).toBeCloseTo(
        ((row.b.price - row.a.price) / row.a.price) * 100,
        7,
      );
      expect(row.difference).toBeCloseTo(row.b.price - row.a.price, 7);
      if (row.b.sources)
        for (const source of row.b.sources) {
          expect(source.id).toBe(row.a.id);
          expect(source.presentation).toBe(row.a.presentation);
          expect(source.units).toBe(row.a.units);
          expect(source.series).toBe(row.a.series);
        }
      if (data.filters.b === "__national__")
        expect(row.b.location_count).toBeGreaterThanOrEqual(2);
    }
    const mean =
      matches.reduce((sum, row) => sum + row.percent, 0) / matches.length;
    expect(data.percent).toBeCloseTo(mean, 7);
    return data;
  }
  try {
    await step(
      "01-native-home-layout",
      async () => {
        await navigate("/");
        await expect(page.locator(".product-card")).toHaveCount(4);
        await expect(page.locator(".mobile-nav")).toBeVisible();
        await layout();
        return { userAgent: native.userAgent, productCards: 4 };
      },
      true,
    );

    await step(
      "02-products-search-save-persistence",
      async () => {
        await navigate("/products");
        await expect(page.locator(".product-card").first()).toBeVisible();
        await page
          .getByLabel("Buscar producto", { exact: true })
          .fill("aguacate");
        await page
          .getByLabel("Buscar producto", { exact: true })
          .press("Escape");
        const card = page.locator(".product-card").first();
        await expect(card).toContainText(/Aguacate/i);
        const name = await card.locator(".product-name").innerText();
        const save = card.getByRole("button", { name: /Guardar/ });
        if (await save.count()) await save.click();
        await navigate("/saved");
        await expect(
          page.locator(".product-name").filter({ hasText: name }),
        ).toBeVisible();
        await page.reload();
        await expect(
          page.locator(".product-name").filter({ hasText: name }),
        ).toBeVisible();
        await layout();
      },
      true,
    );

    await step("03-limon-exact-market-package-current-price", async () => {
      lemon = await fixtureProduct();
      market = lemon.market;
      cityDocument = lemon.data.markets[0].document_id;
      expect(
        lemon.data.history.find((r) => r.date === "2026-09-07")?.price,
      ).toBe(86000);
      await navigate(`/product/${lemon.id}?${lemon.params}`);
      await expect(page.getByTestId("current-product-price")).toHaveText(
        money(lemon.data.current.price),
      );
      await expect(page.getByLabel("Mercado", { exact: true })).toHaveValue(
        market.id,
      );
      await expect(
        page.getByLabel("Presentación", { exact: true }),
      ).toHaveValue("Bulto");
      await expect(page.getByLabel("Unidades", { exact: true })).toHaveValue(
        "24 Kilogramo",
      );
      await expect(filters()).toContainText("Barranquillita");
      await expect(filters()).toContainText("24 Kilogramo");
      await expect(page.locator(".detail-intro .eyebrow")).toContainText(
        /Frutas.*C[ií]tricos/,
      );
      await expect(page.getByLabel("Transporte total (COP)")).toHaveCount(0);
      await expect(page.locator(".market-row")).toHaveCount(1);
      await page.getByText("Ver datos en tabla", { exact: true }).click();
      await descending(".chart-data tbody td:nth-child(2)");
      await layout();
      await captureElement(
        page.locator(".chart-data"),
        "03-price-table-descending",
      );
      await captureElement(filters(), "03-applied-product-filters");
      return {
        market: market.name,
        current: lemon.data.current,
        fixtureSeptember7: 86000,
        package: "Bulto / 24 Kilogramo",
      };
    });

    await step("04-mora-packages-remain-distinct", async () => {
      const fixture = await fixtureProduct(
        "mora-de-castilla",
        "Caja de cartón",
        "2.5 Kilogramo",
      );
      await navigate(`/product/${fixture.id}?${fixture.params}`);
      await expect(page.getByTestId("current-product-price")).toHaveText(
        money(21000),
      );
      screenshot("04-mora-2_5kg-21000");
      await page.getByLabel("Unidades", { exact: true }).click();
      screenshot("04-native-package-selector");
      await device.shell("input keyevent 4");
      await page
        .getByLabel("Unidades", { exact: true })
        .selectOption("12.5 Kilogramo");
      await expect(page.getByLabel("Mercado", { exact: true })).toHaveValue(
        fixture.market.id,
      );
      await expect(page.getByTestId("current-product-price")).toHaveText(
        money(79500),
      );
      await expect(filters()).toContainText("12.5 Kilogramo");
      const q = new URLSearchParams({
        series: "city",
        market: fixture.market.id,
        presentation: fixture.params.get("presentation"),
        units: "12.5 Kilogramo",
        history: "all",
      });
      const data = await get(`/api/products/${fixture.id}?${q}`);
      expect(data.history.find((r) => r.date === "2026-09-07")?.price).toBe(
        79500,
      );
      const base = new URLSearchParams(fixture.params);
      base.delete("market");
      await navigate(`/product/${fixture.id}?${base}`);
      await expect(page.getByTestId("current-product-price")).toHaveText(
        money(21000),
      );
      let delayedMarketRequest = false;
      const pendingDelays = [],
        delayedRoute = "**/api/products/mora-de-castilla?*";
      await page.route(delayedRoute, async (route) => {
        const url = new URL(route.request().url());
        if (
          url.searchParams.get("market") === fixture.market.id &&
          url.searchParams.get("units") === "2.5 Kilogramo"
        ) {
          delayedMarketRequest = true;
          const pause = new Promise((resolve) => setTimeout(resolve, 750));
          pendingDelays.push(pause);
          await pause;
        }
        try {
          await route.continue();
        } catch {
          /* Aborted stale requests need no response. */
        }
      });
      try {
        await page
          .getByLabel("Mercado", { exact: true })
          .selectOption(fixture.market.id);
        await expect.poll(() => delayedMarketRequest).toBe(true);
        await page
          .getByLabel("Unidades", { exact: true })
          .selectOption("12.5 Kilogramo");
        await Promise.all(pendingDelays);
        await expect(page.getByTestId("current-product-price")).toHaveText(
          money(79500),
        );
        await expect(page.getByLabel("Mercado", { exact: true })).toHaveValue(
          fixture.market.id,
        );
        await expect(filters()).toContainText("Barranquillita");
        await captureElement(
          page.locator(".product-price-header"),
          "04-rapid-market-unit-changes-preserve-price",
        );
      } finally {
        await page.unroute(delayedRoute);
      }
      await layout();
      return {
        smallPackage: 21000,
        largePackage: 79500,
        smallKg: 2.5,
        largeKg: 12.5,
        rapidFilterChangesPreservedMarket: true,
        delayedMarketRequestMs: 750,
      };
    });

    await step("05-monthly-history-and-descending-table", async () => {
      await navigate("/product/limon-tahiti?series=monthly&history=all");
      await expect(
        page.getByLabel("Tipo de precio", { exact: true }),
      ).toHaveValue("monthly");
      await expect(page.getByRole("button", { name: "Todo", exact: true })).toHaveCount(0);
      await page.getByText("Ver datos en tabla", { exact: true }).click();
      const prices = await descending(".chart-data tbody td:nth-child(2)");
      expect(prices.length).toBeGreaterThan(12);
      await expect(page.locator(".chart-panel")).not.toContainText(":all");
      await expect(page.getByRole("button", { name: "3 meses", exact: true })).toHaveCount(0);
      await layout();
      return { allHistoryObservations: prices.length };
    });

    await step("06-map-filters-real-popups-and-native-back", async () => {
      const fixture = lemon || (await fixtureProduct());
      await navigate(`/product/${fixture.id}?${fixture.params}`);
      await expect(page.getByTestId("current-product-price")).toHaveText(
        money(fixture.data.current.price),
      );
      await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await expect(dialog.getByLabel("Presentación en mapa")).toHaveValue(
        "Bulto",
      );
      await expect(dialog.getByLabel("Unidades en mapa")).toHaveValue(
        "24 Kilogramo",
      );
      await expect(filters(dialog)).toContainText("Barranquillita");
      await expect(filters(dialog)).not.toContainText("Completo");
      await readableFilters(dialog);
      await captureElement(
        filters(dialog),
        "06-map-filters-wrap-without-clipping",
      );
      await expect(dialog.locator(".colombia-map")).toHaveAttribute(
        "data-ready",
        "true",
      );
      await option(
        dialog.getByLabel("Abrir precios de un departamento"),
        /atlantico/,
      );
      await expect(dialog.locator(".map-price-popup")).toBeVisible();
      await expect(dialog.locator(".map-popup-price")).toHaveText(money(86000));
      await expect(dialog.locator(".map-price-popup")).toContainText(
        "Barranquillita",
      );
      let lastPopupPosition = "",
        popupStableSince = 0;
      await expect
        .poll(
          async () => {
            const boxes = await dialog.evaluate((el) => {
              const p = el
                  .querySelector(".maplibregl-popup")
                  .getBoundingClientRect(),
                m = el.querySelector(".colombia-map").getBoundingClientRect();
              return {
                signature: [p.x, p.y, p.width, p.height]
                  .map((n) => Math.round(n))
                  .join(","),
                withinMap:
                  p.top >= m.top - 1 &&
                  p.bottom <= m.bottom + 1 &&
                  p.left >= m.left - 1 &&
                  p.right <= m.right + 1,
              };
            });
            if (boxes.signature !== lastPopupPosition) {
              lastPopupPosition = boxes.signature;
              popupStableSince = Date.now();
            }
            return boxes.withinMap && Date.now() - popupStableSince >= 300;
          },
          {
            timeout: 10000,
            message: "Settled price popup should fit inside the map",
          },
        )
        .toBe(true);
      await captureElement(
        dialog.locator(".map-price-popup"),
        "06-settled-map-price-popup",
      );
      await expect(dialog.locator(".map-results")).toHaveCount(0);
      screenshot("06-map-barranquillita-popup");
      await device.shell("input keyevent 4");
      await expect(dialog).toHaveCount(0);
      await expect(page.getByTestId("current-product-price")).toHaveText(
        money(86000),
      );
      expect(await page.evaluate(() => document.body.style.overflow)).not.toBe(
        "hidden",
      );
      return { popupPrice: 86000, nativeBackClosedOverlay: true };
    });

    await step("07-city-list-links-preserve-market", async () => {
      await navigate("/regional?q=Limón tahití");
      await option(page.getByLabel("Mercado del informe"), /barranquillita/);
      await expect(page.locator(".input-card")).toHaveCount(1);
      await expect(page.locator(".input-card")).toContainText(
        /Frutas.*C[ií]tricos/,
      );
      await page.locator(".input-card h2 a").click();
      await expect(page.getByTestId("current-product-price")).toHaveText(
        money(86000),
      );
      await expect(filters()).toContainText("Barranquillita");
      await layout();
    });

    await step("08-source-pdf-native-render-paging-download", async () => {
      const fixture = lemon || (await fixtureProduct());
      const doc = fixture.data.markets[0];
      await navigate(`/product/${fixture.id}?${fixture.params}`);
      await page
        .getByRole("link", {
          name: "Consultar fuente del precio actual",
          exact: true,
        })
        .click();
      await expect(page.locator("canvas[data-rendered=true]")).toBeVisible();
      await expect(page.getByLabel("Página del documento")).toHaveValue(
        String(doc.source_page),
      );
      await expect(page.locator(".pdf-text")).toContainText("Barranquillita");
      screenshot("08-original-city-pdf");
      const next = page.getByRole("button", {
        name: "Siguiente →",
        exact: true,
      });
      await expect(next).toBeEnabled();
      await next.click();
      await expect(page.getByLabel("Página del documento")).toHaveValue(
        String(doc.source_page + 1),
      );
      await expect(page.locator("canvas[data-rendered=true]")).toHaveAttribute(
        "aria-label",
        `Página ${doc.source_page + 1} del PDF`,
      );
      const width = await page
        .locator("canvas[data-rendered=true]")
        .evaluate((canvas) => canvas.width);
      await page.getByLabel("Tamaño del documento").selectOption("2");
      await expect
        .poll(async () =>
          page
            .locator("canvas[data-rendered=true]")
            .evaluate((canvas) => canvas.width),
        )
        .toBeGreaterThan(width);
      await captureElement(
        page.locator("canvas[data-rendered=true]"),
        "08-pdf-page-two-200-percent",
      );
      const pdfScroll = page.locator(".pdf-paper");
      expect(
        await pdfScroll.evaluate((el) => el.scrollWidth > el.clientWidth),
      ).toBe(true);
      await pdfScroll.evaluate((el) => {
        el.scrollLeft = el.scrollWidth - el.clientWidth;
      });
      await expect
        .poll(async () => pdfScroll.evaluate((el) => el.scrollLeft))
        .toBeGreaterThan(0);
      screenshot("08-pdf-zoom-scroll-to-price-columns");
      const download = await nativeDownload(doc.document_id, "pdf");
      await device.shell("input keyevent 4");
      await expect(page).toHaveURL(/\/product\/limon-tahiti/);
      return {
        documentId: doc.document_id,
        page: doc.source_page,
        nextPage: doc.source_page + 1,
        ...download,
      };
    });

    await step("09-excel-in-app-read-only-sheet-row-zoom", async () => {
      const data = await get(
        "/api/references?publisher=World+Bank&q=ar%C3%A1bica",
      );
      expect(data.rows.length).toBeGreaterThan(0);
      workbookDocument = data.rows[0].document_id;
      const reference = data.rows[0],
        cell = reference.source_locator.match(/^(.+)!([A-Z]+)(\d+)$/);
      expect(cell).toBeTruthy();
      await navigate("/references/" + reference.quote_key);
      await page
        .locator(".product-price-header")
        .getByRole("link", { name: "Consultar fuente", exact: true })
        .click();
      const viewer = page.getByRole("region", {
        name: "Visor de Excel de solo lectura",
      });
      await expect(viewer).toBeVisible();
      await expect(viewer.locator("tbody tr").first()).toBeVisible();
      await expect(viewer.getByLabel("Hoja del archivo Excel")).toHaveValue(
        cell[1],
      );
      await expect(viewer.locator("tbody tr").first().locator("th")).toHaveText(
        cell[3],
      );
      const column =
        [...cell[2]].reduce(
          (n, letter) => n * 26 + letter.charCodeAt(0) - 64,
          0,
        ) - 1;
      await expect(
        viewer.locator("tbody tr").first().locator("td").nth(column),
      ).toHaveText(Number(reference.price).toLocaleString("es-CO"));
      await captureElement(
        viewer.locator(".workbook-range"),
        "09-excel-source-locator-opens-quoted-row",
      );
      await viewer
        .getByLabel("Hoja del archivo Excel")
        .selectOption("Description");
      await viewer
        .getByLabel("Hoja del archivo Excel")
        .selectOption("Monthly Prices");
      await expect(viewer.locator(".workbook-range")).toContainText(
        "Monthly Prices",
      );
      await expect(viewer.locator("tbody tr").first()).toContainText(
        "World Bank",
      );
      await expect(
        viewer.locator(
          "tbody [contenteditable=true],tbody input,tbody textarea",
        ),
      ).toHaveCount(0);
      await viewer.getByLabel(/^Zoom/).selectOption("1.5");
      await expect(viewer.locator("table")).toHaveCSS("font-size", "21px");
      screenshot("09-excel-read-only-zoom");
      await viewer.getByLabel("Ir a la fila").fill("799");
      await viewer.getByLabel("Ir a la fila").press("Enter");
      await expect(viewer.locator("tbody tr").first()).toContainText("2026M01");
      await expect(viewer.locator("tbody tr").first().locator("th")).toHaveText(
        "799",
      );
      await captureElement(
        viewer.locator(".workbook-range"),
        "09-excel-january-2026-read-only",
      );
      await viewer.locator(".workbook-scroll").evaluate((el) => {
        el.scrollLeft = 500;
      });
      await expect
        .poll(async () =>
          viewer.locator(".workbook-scroll").evaluate((el) => el.scrollLeft),
        )
        .toBeGreaterThan(0);
      await expect(
        viewer.getByRole("button", { name: "Siguientes filas →" }),
      ).toBeDisabled();
      await viewer
        .getByLabel("Hoja del archivo Excel")
        .selectOption("Description");
      await expect(viewer.locator(".workbook-range")).toContainText(
        "Description",
      );
      await expect(viewer.locator("tbody")).toContainText("Coffee, Arabica");
      await layout();
      return {
        documentId: workbookDocument,
        sourceLocator: reference.source_locator,
        linkedSourcePriceCellMatches: true,
        sheetsVisited: ["Monthly Prices", "Description"],
        numericDataRow: 799,
        readOnly: true,
      };
    });

    await step("10-historical-excel-native-download-hash", async () => {
      const alias = "daily-2012-06-12-workbook";
      await navigate("/evidence/" + alias);
      await expect(
        page.getByRole("region", { name: "Visor de Excel de solo lectura" }),
      ).toBeVisible();
      await expect(
        page.locator(".workbook-viewer tbody tr").first(),
      ).toBeVisible();
      return { alias, ...(await nativeDownload(alias, "xls")) };
    });

    await step(
      "11-image-credits-all-bottom-tabs",
      async () => {
        await navigate("/credits");
        await expect(
          page.getByRole("heading", { name: "Créditos de imágenes" }),
        ).toBeVisible();
        const targets = await page
          .locator(".mobile-nav a")
          .evaluateAll((nodes) =>
            nodes.map((a) => ({
              href: a.getAttribute("href"),
              label: a.textContent.trim(),
            })),
          );
        expect(targets.length).toBe(5);
        for (let i = 0; i < targets.length; i++) {
          await navigate("/credits");
          await page
            .locator(".credits-grid article")
            .last()
            .scrollIntoViewIfNeeded();
          const link = page.locator(`.mobile-nav a[href="${targets[i].href}"]`);
          await expect(link).toBeVisible();
          expect(
            await link.evaluate((el) => {
              const b = el.getBoundingClientRect();
              return el.contains(
                document.elementFromPoint(
                  b.x + b.width / 2,
                  b.y + b.height / 2,
                ),
              );
            }),
          ).toBe(true);
          await link.click();
          await expect(page).toHaveURL(origin + targets[i].href);
          await expect(page.locator(".mobile-nav")).toBeVisible();
          await layout();
          screenshot("11-credit-nav-" + i);
        }
        return { tabs: targets, allHitTargetsUnobstructed: true };
      },
      true,
    );

    await step("12-market-expand-all-prices", async () => {
      const fixture = lemon || (await fixtureProduct());
      await navigate("/market/" + fixture.market.id);
      await expect(
        page.getByRole("heading", { name: "Precios en este mercado" }),
      ).toBeVisible();
      await page.getByLabel(/^Tipo de precio/).selectOption("city");
      const data = await get(
        `/api/compare/markets?a=${fixture.market.id}&view=prices&series=city`,
      );
      expect(data.rows.length).toBeGreaterThan(12);
      const section = page.locator("section").filter({
        has: page.getByRole("heading", {
          name: "Precios en este mercado",
          exact: true,
        }),
      });
      await expect(section.locator("article")).toHaveCount(12);
      await section
        .getByRole("button", { name: "Expandir lista completa", exact: true })
        .click();
      await expect(section.locator("article")).toHaveCount(data.rows.length);
      await expect(filters(section)).toContainText("Barranquillita");
      await captureElement(
        section.locator("article").first(),
        "12-market-list-expanded",
      );
      await section
        .getByRole("button", { name: "Mostrar menos", exact: true })
        .click();
      await expect(section.locator("article")).toHaveCount(12);
      await section
        .getByRole("link", { name: "Comparar con otro mercado", exact: true })
        .click();
      await expect(page).toHaveURL(/\/compare\/markets\?/);
      await expect(filters()).toContainText("Barranquillita");
      return { totalCombinations: data.rows.length, collapsedCount: 12 };
    });

    await step("13-market-national-comparison-arithmetic-filters", async () => {
      const fixture = lemon || (await fixtureProduct());
      const params = new URLSearchParams({
        a: fixture.market.id,
        series: "city",
        b: "__national__",
        history: "recent",
      });
      const data = await comparison("markets", params);
      await navigate("/compare/markets?" + params);
      const result = page.getByRole("region", {
        name: "Resultado de la comparación",
      });
      await expect(result.locator("strong")).toHaveText(percent(data.percent));
      await expect(filters()).toContainText("Promedio de Colombia");
      await expect(page.getByLabel(/^Período/)).toHaveCount(0);
      const input = page.getByLabel("Buscar producto", { exact: true });
      await input.fill("limón");
      await expect(filters()).toContainText("limón");
      await page.getByLabel(/^Mostrar/).selectOption("matched");
      const selected = data.rows.filter(
        (r) => r.b && fold(r.a.name).includes("limon"),
      );
      expect(selected.length).toBeGreaterThan(0);
      const expected =
        selected.reduce((sum, r) => sum + r.percent, 0) / selected.length;
      await expect(result.locator("strong")).toHaveText(percent(expected));
      await captureElement(result, "13-colombia-comparison-calculated-result");
      await expect(filters()).toContainText("Solo coincidencias");
      await layout();
      return {
        matched: data.matched,
        allPercent: data.percent,
        filteredPercent: expected,
      };
    });

    await step("14-market-pair-comparison-and-date-matching", async () => {
      const data = await comparison("markets", "series=monthly");
      const alternative = data.locations.find(
        (l) =>
          l.id !== data.filters.a &&
          (!l.series || l.series.includes("monthly")),
      );
      expect(alternative).toBeTruthy();
      const params = new URLSearchParams({
        a: data.filters.a,
        b: alternative.id,
        series: "monthly",
        dates: "same",
      });
      const pair = await get("/api/compare/markets?" + params);
      for (const row of pair.rows.filter((r) => r.b))
        expect(row.b.date_to).toBe(row.a.date);
      await navigate("/compare/markets?" + params);
      await expect(filters()).toContainText("Solo fechas iguales");
      await expect(filters()).toContainText(alternative.name);
      await expect(page.getByLabel("B · Comparar con")).toHaveValue(
        alternative.id,
      );
      await layout();
      return {
        a: pair.a_name,
        b: pair.b_name,
        matched: pair.matched,
        dates: "same",
      };
    });

    await step("15-insumos-comparison-commercial-identity", async () => {
      const data = await comparison("inputs", "scope=department");
      await navigate("/compare/inputs?scope=department");
      await expect(
        page.getByRole("heading", { name: "Comparar insumos" }),
      ).toBeVisible();
      await expect(
        page
          .getByRole("region", { name: "Resultado de la comparación" })
          .locator("strong"),
      ).toHaveText(percent(data.percent));
      await page
        .getByLabel("Buscar insumo, marca o ICA", { exact: true })
        .fill("urea");
      await expect(filters()).toContainText("urea");
      await expect(filters()).toContainText("Departamentos");
      await page.getByLabel(/^Cobertura/).selectOption("municipality");
      await expect(filters()).toContainText("Municipios");
      await expect(
        page.getByRole("region", { name: "Resultado de la comparación" }),
      ).toBeVisible();
      const municipal = await comparison("inputs", "scope=municipality");
      await layout();
      return {
        departmentMatches: data.matched,
        municipalMatches: municipal.matched,
        exactIdentityChecked: true,
      };
    });

    await step(
      "16-official-references-currency-history-and-method",
      async () => {
        const data = await get("/api/catalog");
        const arabica = data.products.find(
          (r) =>
            r.kind === "official-reference" &&
            r.source === "World Bank" &&
            fold(r.name).includes("arabica"),
        );
        expect(arabica).toBeTruthy();
        await navigate("/products");
        await page
          .getByLabel("Buscar producto", { exact: true })
          .fill("arábica");
        await page
          .getByLabel("Buscar producto", { exact: true })
          .press("Escape");
        await page.getByLabel("Moneda", { exact: true }).selectOption("USD");
        const card = page.locator(
          ".product-card[data-catalog-identity=" +
            JSON.stringify(arabica.identity) +
            "]",
        );
        await expect(card).toBeVisible();
        await expect(filters()).toContainText("USD");
        await expect(card.locator(".product-price")).toContainText("kg");
        await card.locator(".product-name").click();
        await expect(page.locator(".current-product-price")).toContainText(
          Number(arabica.price).toLocaleString("es-CO", {
            maximumFractionDigits: 4,
          }),
        );
        await expect(filters()).toContainText("USD");
        await page
          .getByRole("combobox", { name: /^Historial/ })
          .selectOption("all");
        await expect(page.locator(".chart-panel")).toContainText("1960");
        await page.getByText("Ver datos en tabla", { exact: true }).click();
        const values = await descending(".chart-data tbody td:nth-child(2)");
        expect(values.length).toBeGreaterThan(700);
        await page
          .getByText(
            /^(Descripción y método de la fuente|Fuente y método del precio)$/,
          )
          .click();
        await expect(page.locator(".reference-metadata")).toContainText(
          "other mild Arabicas",
        );
        await layout();
        return {
          originalCurrency: "USD",
          currentArabica: arabica.price,
          historicalMonths: values.length,
        };
      },
    );

    await step("17-official-flowers-ranges-and-oil-tonnes", async () => {
      const flowers = await get("/api/references?publisher=USDA+AMS&q=Clavel");
      expect(flowers.rows.length).toBeGreaterThan(1);
      expect(new Set(flowers.rows.map((r) => r.quote_key)).size).toBe(
        flowers.rows.length,
      );
      const colombia = flowers.rows.find(
        (r) =>
          r.details.origin === "COLOMBIA" &&
          r.details.source_product === "CARNATIONS",
      );
      expect(colombia).toBeTruthy();
      await navigate("/references/" + colombia.quote_key);
      await expect(page.locator(".product-price-header")).toContainText(
        "Punto medio calculado",
      );
      await expect(filters()).toContainText("USD");
      await expect(filters()).toContainText("per stem");
      await page
        .getByText(
          /^(Descripción y método de la fuente|Fuente y método del precio)$/,
        )
        .click();
      await expect(page.locator(".reference-metadata")).toContainText(
        "COLOMBIA",
      );
      screenshot("17-colombian-flower-us-terminal-price");
      const oil = await get(
        "/api/references?publisher=World+Bank&q=aceite+de+coco",
      );
      expect(oil.rows[0].unit).toBe("tonne");
      await navigate("/references/" + oil.rows[0].quote_key);
      await expect(filters()).toContainText("tonne");
      await expect(filters()).toContainText("USD");
      await layout();
      return {
        flowerCurrency: colombia.currency,
        flowerUnit: colombia.unit,
        fullRange: [colombia.min_price, colombia.max_price],
        coconutUnit: oil.rows[0].unit,
      };
    });

    await step("18-expanded-inputs-visible-filter-state", async () => {
      await navigate("/insumos");
      await expect(page.locator(".input-catalog-card").first()).toBeVisible();
      expect(
        await page.locator(".catalog-heading").evaluate((el) => {
          const heading = el.querySelector("h1").getBoundingClientRect(),
            actions = el
              .querySelector(".detail-actions")
              .getBoundingClientRect();
          return (
            heading.bottom <= actions.top ||
            actions.bottom <= heading.top ||
            heading.right <= actions.left ||
            actions.right <= heading.left
          );
        }),
      ).toBe(true);
      await captureElement(
        page.locator(".catalog-heading"),
        "18-insumos-heading-actions-without-overlap",
      );
      expect(
        await page.locator(".category-filters button").count(),
      ).toBeGreaterThanOrEqual(15);
      await page
        .getByLabel("Cobertura del precio")
        .selectOption("municipality");
      await expect(page.locator(".input-catalog-card").first()).toBeVisible();
      await expect(page.getByLabel(/^Período/)).toHaveCount(0);
      await page.getByLabel("Buscar insumo", { exact: true }).fill("urea");
      await page.getByLabel("Buscar insumo", { exact: true }).press("Escape");
      await expect(filters()).toContainText(/municip/i);
      await expect(filters()).toContainText("urea");
      await expect(filters()).not.toContainText(/12 meses|Todo el histórico/i);
      const catalogMapRequest = page.waitForResponse((r) => {
        const u = new URL(r.url());
        return (
          u.pathname === "/api/explore/map" &&
          u.searchParams.get("kind") === "input" &&
          u.searchParams.get("query") === "urea" &&
          Boolean(u.searchParams.get("id"))
        );
      });
      await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
      let dialog = page.getByRole("dialog");
      await expect(filters(dialog)).toContainText("urea");
      await expect(filters(dialog)).toContainText("Municipio");
      await expect(filters(dialog)).toContainText("urea");
      const catalogMap = await catalogMapRequest;
      expect(catalogMap.status()).toBe(200);
      const catalogFilters = (await catalogMap.json()).filters;
      expect(catalogFilters.scope).toBe("municipality");
      expect(catalogFilters.history).toBe("recent");
      await readableFilters(dialog);
      await captureElement(
        filters(dialog),
        "18-input-catalog-map-filter-state",
      );
      await device.shell("input keyevent 4");
      await expect(dialog).toHaveCount(0);
      await page.locator(".input-catalog-card").first().click();
      await expect(page.locator("h1")).toContainText(/urea/i);
      await expect(filters()).toBeVisible();
      const selected = new URL(page.url()),
        inputId = selected.pathname.split("/").at(-1);
      expect(selected.searchParams.get("municipality")).toBeTruthy();
      const detailMapRequest = page.waitForResponse((r) => {
        const u = new URL(r.url());
        return (
          u.pathname === "/api/explore/map" &&
          u.searchParams.get("kind") === "input" &&
          u.searchParams.get("id") === inputId
        );
      });
      await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
      dialog = page.getByRole("dialog");
      const detailResponse = await detailMapRequest;
      expect(detailResponse.status()).toBe(200);
      const detailFilters = (await detailResponse.json()).filters;
      expect(detailFilters.scope).toBe("municipality");
      expect(detailFilters.history).toBe("recent");
      expect(detailFilters.region).toBe(
        selected.searchParams.get("department"),
      );
      expect(detailFilters.municipality).toBe(
        selected.searchParams.get("municipality"),
      );
      await expect(filters(dialog)).toContainText(
        selected.searchParams.get("municipality"),
      );
      await readableFilters(dialog);
      await captureElement(
        filters(dialog),
        "18-input-detail-map-municipality-filters",
      );
      await device.shell("input keyevent 4");
      await expect(dialog).toHaveCount(0);
      await layout();
      return {
        catalogQueryPreserved: true,
        scope: "municipality",
        history: "all",
        municipalityPreservedInDetailMap: true,
      };
    });

    await step(
      "19-coffee-carga-unit-arithmetic",
      async () => {
        await navigate("/coffee");
        await page.getByLabel("Cantidad", { exact: true }).fill("125");
        await page.getByLabel("Unidad", { exact: true }).selectOption("1");
        await page
          .getByLabel("Oferta del comprador por carga (COP)")
          .fill("2100000");
        await page
          .getByLabel("Transporte y descuentos totales (COP)")
          .fill("50000");
        await expect(page.locator(".calculation-result>strong")).toHaveText(
          money(2050000),
        );
        await page.getByLabel("Cantidad", { exact: true }).fill("10");
        await page.getByLabel("Unidad", { exact: true }).selectOption("12.5");
        await expect(page.locator(".calculation-result>strong")).toHaveText(
          money(2050000),
        );
        await page.getByLabel("Cantidad", { exact: true }).fill("-1");
        await expect(page.locator(".invalid-input")).toBeVisible();
        await expect(page.locator(".calculation-result>strong")).toHaveText(
          "—",
        );
        await layout();
      },
      true,
    );

    await step(
      "20-farm-map-layers-and-finance-navigation",
      async () => {
        await navigate("/farm");
        const example = page.getByRole("button", {
          name: "Explorar ejemplo en Pitalito",
        });
        if (await example.isVisible()) await example.click();
        const map = page.getByRole("region", {
          name: "Mapa de capas de mi finca",
        });
        await expect(map).toHaveAttribute("data-ready", "true");
        await expect(
          page
            .getByRole("group", { name: "Capas del mapa" })
            .getByRole("button"),
        ).toHaveCount(6);
        await page
          .getByLabel("Horizonte de la información")
          .selectOption("month");
        await page.getByLabel("Mes habitual").selectOption("9");
        await expect(map).toHaveAttribute("data-layer", "rain-month");
        await expect(page.getByLabel("Mes habitual")).toHaveValue("9");
        await page
          .getByRole("button", { name: "Temperatura", exact: true })
          .click();
        await expect(map).toHaveAttribute("data-layer", "temperature-month");
        await page
          .getByLabel("Horizonte de la información")
          .selectOption("year");
        await expect(map).toHaveAttribute("data-layer", "temperature-year");
        await expect(page.getByLabel("Mes habitual")).toHaveCount(0);
        await map.scrollIntoViewIfNeeded();
        screenshot("20-farm-temperature-map");
        await page.getByRole("tab", { name: /Costos y rentabilidad/ }).click();
        await expect(page.locator("#clean-panel")).toBeVisible();
        await expect(page.locator("#zone-panel")).toBeHidden();
        await page.getByRole("tab", { name: /Explorar mi zona/ }).click();
        await expect(
          page.getByLabel("Horizonte de la información"),
        ).toHaveValue("year");
        await expect(map).toHaveAttribute("data-layer", "temperature-year");
        await layout();
      },
      true,
    );

    await step(
      "21-budget-calculation-save-and-invalid-input",
      async () => {
        await navigate("/plan?tab=budget");
        await page.getByLabel("Área (hectáreas)", { exact: true }).fill("2");
        await page
          .getByLabel("Cosecha de referencia (kg por hectárea)")
          .fill("1000");
        await page.getByLabel("Pérdida o producto no vendible (%)").fill("10");
        for (const [label, value] of [
          ["Preparación, siembra y labores por hectárea", "200000"],
          ["Semilla e insumos por hectárea", "300000"],
          ["Cosecha y poscosecha por hectárea", "100000"],
          ["Otros costos de producción por hectárea", "0"],
        ])
          await page.getByLabel(label, { exact: true }).fill(value);
        await page
          .getByRole("button", { name: "Ingresar mi precio", exact: true })
          .click();
        await page
          .getByLabel("Precio que recibirías por kg (COP)")
          .fill("2000");
        await page
          .getByLabel("Gastos adicionales de venta, total (COP)")
          .fill("100000");
        await page.getByLabel("Comisión sobre la venta (%)").fill("10");
        await expect(
          page.locator(".earnings-scenarios .typical strong"),
        ).toHaveText(money(1940000));
        await page
          .getByRole("button", { name: "Guardar escenario", exact: true })
          .click();
        await expect(page.locator(".saved-scenarios")).toContainText(
          money(1940000),
        );
        await page
          .getByLabel("Cosecha de referencia (kg por hectárea)")
          .fill("0");
        await expect(
          page.getByRole("button", { name: "Guardar escenario", exact: true }),
        ).toBeDisabled();
        await layout();
      },
      true,
    );

    await step(
      "22-offers-arithmetic-and-reload",
      async () => {
        await navigate("/offers");
        await page.getByLabel("Cantidad total que comparas (kg)").fill("250");
        await page.getByLabel("Unidad de las cotizaciones").selectOption("125");
        await page
          .getByLabel("Precio oferta 1", { exact: true })
          .fill("2000000");
        await page.getByLabel("Kilos oferta 1", { exact: true }).fill("250");
        await page.getByLabel("Descuento oferta 1", { exact: true }).fill("5");
        await page
          .getByLabel("Transporte oferta 1", { exact: true })
          .fill("100000");
        await page.getByLabel("Empaque oferta 1", { exact: true }).fill("0");
        await page.getByLabel("Gastos oferta 1", { exact: true }).fill("0");
        await expect(page.locator(".offer-result strong").first()).toHaveText(
          money(3700000),
        );
        await page.reload();
        await expect(
          page.getByLabel("Precio oferta 1", { exact: true }),
        ).toHaveValue("2000000");
        await layout();
      },
      true,
    );

    await step(
      "23-api-failure-visible-retry",
      async () => {
        await page.route("**/api/catalog*", (route) =>
          route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({ error: "Simulator validation" }),
          }),
        );
        try {
          await navigate("/products");
          await expect(page.locator("main").getByRole("alert")).toContainText(
            "No pudimos cargar los datos",
          );
        } finally {
          await page.unroute("**/api/catalog*");
        }
        await page.getByRole("button", { name: "Volver a intentar" }).click();
        await expect(page.locator(".product-card").first()).toBeVisible();
      },
      true,
    );

    await step("24-native-network-error-recovery", async () => {
      await navigate("/offers");
      await page.getByLabel("Precio oferta 1", { exact: true }).fill("2000000");
      if (
        !["0", "1"].includes(networkBefore.wifi) ||
        !["0", "1"].includes(networkBefore.data)
      )
        throw Error("Cannot safely restore original emulator network settings");
      await device.shell("svc wifi disable");
      await device.shell("svc data disable");
      await expect
        .poll(async () =>
          (await shell("dumpsys connectivity"))
            .split("\n")
            .some(
              (l) =>
                l.includes("NetworkAgentInfo{") && l.includes("IS_VALIDATED"),
            ),
        )
        .toBe(false);
      await device.shell("am force-stop co.agroamigo.demo");
      await device.shell("am start -n co.agroamigo.demo/.MainActivity");
      await expect
        .poll(
          async () =>
            (
              await shell(
                "uiautomator dump /sdcard/agro-validation.xml && cat /sdcard/agro-validation.xml",
              )
            ).includes("Volvamos a conectar"),
          { timeout: 30000 },
        )
        .toBe(true);
      screenshot("24-native-offline-message");
      await device.shell("svc wifi enable");
      await waitForNetwork();
      await device.shell("input keyevent 4");
      page = await (await device.webView({ pkg: "co.agroamigo.demo" })).page();
      watchPage(page);
      page.setDefaultTimeout(60000);
      page.setDefaultNavigationTimeout(90000);
      await expect(page.locator(".product-card")).toHaveCount(4);
      await navigate("/offers");
      await expect(
        page.getByLabel("Precio oferta 1", { exact: true }),
      ).toHaveValue("2000000");
      return {
        nativeErrorVisible: true,
        recoveredWithoutClearingPersonalData: true,
      };
    });

    await step("25-farm-exact-coordinates-persistence-weather", async () => {
      await navigate("/farm");
      // Real Android geolocation from the dedicated emulator's GPS provider.
      // The caller sets its test point to 1.912345,-76.123456 before this case.
      await expect(page.getByLabel("Latitud de la finca", { exact: true })).toHaveCount(0);
      await page.getByRole("button", { name: "Usar mi ubicación", exact: true }).click();
      const map = page.getByRole("region", {
        name: "Mapa de capas de mi finca",
      });
      await expect(map).toHaveAttribute("data-ready", "true");
      await expect.poll(async () => Number(await map.getAttribute("data-pin-lat"))).toBeCloseTo(1.912345,4);
      const actualLat=Number(await map.getAttribute("data-pin-lat"));
      const actualLon=Number(await map.getAttribute("data-pin-lon"));
      expect(actualLon).toBeCloseTo(-76.123456,4);
      const expectedLat=actualLat.toFixed(6), expectedLon=actualLon.toFixed(6);
      const activeProfileMatches = () =>
        page.evaluate(({expectedLat,expectedLon}) => {
          const store = JSON.parse(
            localStorage.getItem("agroamigo-farms-v2") || "null",
          );
          const active = store?.farms.find((f) => f.id === store.activeId);
          const location = JSON.parse(
            localStorage.getItem("agroamigo-location-v1") || "null",
          );
          return (
            active?.profile.latitude === expectedLat &&
            active.profile.longitude === expectedLon &&
            active.profile.locationMethod === "gps" &&
            location.farmId === active.id
          );
        },{expectedLat,expectedLon});
      expect(await activeProfileMatches()).toBe(true);
      await captureElement(
        page.locator(".location-toolbar"),
        "25-native-gps-farm-pin",
      );
      await page.reload({ waitUntil: "domcontentloaded" });
      expect(Number(await map.getAttribute("data-pin-lat"))).toBeCloseTo(actualLat,5);
      expect(Number(await map.getAttribute("data-pin-lon"))).toBeCloseTo(actualLon,5);
      expect(await activeProfileMatches()).toBe(true);
      await page
        .getByLabel("Buscar municipio", { exact: true })
        .fill("Popayán");
      await page.getByRole("option", { name: /POPAYÁN.*CAUCA/i }).click();
      await expect(page.locator(".location-message")).toContainText(
        "La selección no cambia tu pin",
      );
      expect(Number(await map.getAttribute("data-pin-lat"))).toBeCloseTo(actualLat,5);
      expect(Number(await map.getAttribute("data-pin-lon"))).toBeCloseTo(actualLon,5);
      expect(await activeProfileMatches()).toBe(true);
      const weatherRequest = page.waitForResponse((r) => {
        const url = new URL(r.url());
        return (
          url.pathname === "/api/planning/weather" &&
          url.searchParams.get("lat") === expectedLat &&
          url.searchParams.get("lon") === expectedLon
        );
      });
      await page
        .getByLabel("Horizonte de la información")
        .selectOption("forecast");
      expect((await weatherRequest).status()).toBe(200);
      await expect(page.locator(".forecast-day-strip > div")).toHaveCount(7);
      await captureElement(
        page.locator(".zone-readings"),
        "25-exact-pin-seven-day-weather",
      );
      await expect(page.getByLabel("Latitud de la finca", { exact: true })).toHaveCount(0);
      await expect(page.getByLabel("Longitud de la finca", { exact: true })).toHaveCount(0);
      const weather = page.getByRole("region", { name: "Tiempo y pronóstico de mi finca" });
      await expect(weather).toContainText("estimación del modelo");
      await weather.getByRole("button", { name: "Próximos 7 días", exact: true }).click();
      await expect(weather.locator("article")).toHaveCount(7);
      await captureElement(weather, "25-current-weather-and-forecast");
      expect(await activeProfileMatches()).toBe(true);
      await layout();
      return {
        latitude: actualLat,
        longitude: actualLon,
        activeFarmLinked: true,
        preservedAfterReloadAndMunicipalityChange: true,
        nativeGpsAndForecastPassed: true,
        forecastDays: 7,
      };
    });
    await step("26-historical-supply-months-totals-and-source", async () => {
      const marketId = "sipsa-armenia-mercar";
      const tonnes = (kg) =>
        new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(
          Number(kg) / 1000,
        );
      await navigate("/market/" + marketId);
      await page
        .getByRole("tab", { name: "Abastecimiento", exact: true })
        .click();
      const controls = page.getByRole("region", {
        name: "Filtros de abastecimiento",
      });
      const months = page.getByRole("combobox", { name: /^Mes de consulta/ });
      await expect(controls.getByRole("combobox")).toHaveCount(1);
      await expect(
        page.getByRole("combobox", { name: /^Historial de abastecimiento/ }),
      ).toHaveCount(0);
      await expect(months).toBeEnabled();
      await expect(months.locator('option[value="2019-01-01"]')).toHaveCount(1);
      await expect(months.locator('option[value="2020-01-01"]')).toHaveCount(1);
      await expect(months).toBeEnabled();
      const content = page.locator(".supply-content");
      const availableMonths = await months
        .locator("option")
        .evaluateAll((options) => options.map((o) => o.value));
      expect(availableMonths.length).toBeGreaterThanOrEqual(153);
      expect(new Set(availableMonths).size).toBe(availableMonths.length);
      expect(availableMonths).toEqual([...availableMonths].sort().reverse());
      const verifyMonth = async (month) => {
        const response = page.waitForResponse((r) => {
          const u = new URL(r.url());
          return (
            u.pathname === "/api/explore/supply" &&
            u.searchParams.get("market") === marketId &&
            u.searchParams.get("history") === "all" &&
            u.searchParams.get("month") === month
          );
        });
        await months.selectOption(month);
        const res = await response;
        expect(res.status()).toBe(200);
        const data = await res.json();
        expect(data.selected_period).toBe(month);
        expect(data.rows.length).toBeGreaterThan(0);
        expect(
          data.rows.every(
            (r) => r.period_start === month && r.market_id === marketId,
          ),
        ).toBe(true);
        const total = data.rows.reduce(
          (sum, r) => sum + Number(r.quantity_kg),
          0,
        );
        expect(total).toBeGreaterThan(0);
        expect(
          Number(data.history.find((h) => h.date === month).quantity_kg),
        ).toBeCloseTo(total, 6);
        await expect(content.locator(".supply-summary h2")).toHaveText(
          tonnes(total) + " toneladas",
        );
        const rows = content.locator(".supply-list > article");
        await expect(rows).toHaveCount(data.rows.length);
        expect(
          await rows.evaluateAll((nodes) =>
            nodes.map((el) => ({
              name: el.querySelector(
                "div:first-child > a, div:first-child > strong",
              ).textContent,
              tonnes: el.querySelector("div:last-child > strong").textContent,
            })),
          ),
        ).toEqual(
          data.rows.map((r) => ({
            name: r.food_name,
            tonnes: tonnes(r.quantity_kg) + " t",
          })),
        );
        await expect(filters(content)).toContainText("Mercar");
        await expect(filters(content)).toContainText(month.slice(0, 4));
        await expect(filters(content)).toContainText("DANE SIPSA-A");
        await readableFilters(content);
        return { data, total };
      };
      const january2019 = await verifyMonth("2019-01-01");
      expect(availableMonths).toEqual(
        january2019.data.history.map((h) => h.date).reverse(),
      );
      await captureElement(
        page.getByRole("region", { name: "Filtros de abastecimiento" }),
        "26-historical-supply-controls-january-2019",
      );
      const bars = content.getByLabel("Abastecimiento mensual en toneladas", {
        exact: true,
      });
      await expect(
        bars.getByRole("button", { name: /^enero de 2019:/ }),
      ).toHaveAttribute("aria-pressed", "true");
      expect(await bars.locator("button small").allTextContents()).toEqual(
        january2019.data.history.map((h) =>
          new Date(h.date + "T12:00:00Z").toLocaleDateString("es-CO", {
            month: "short",
            year: "2-digit",
            timeZone: "America/Bogota",
          }),
        ),
      );
      expect(await bars.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(
        true,
      );
      await bars.evaluate((el) => {
        el.scrollLeft = el.scrollWidth - el.clientWidth;
      });
      await expect
        .poll(async () => bars.evaluate((el) => el.scrollLeft))
        .toBeGreaterThan(0);
      await captureElement(
        bars,
        "26-history-bars-year-labels-horizontal-scroll",
      );
      await layout();
      const firstRow = january2019.data.rows[0];
      const source = content
        .locator(".supply-list > article")
        .first()
        .getByRole("link", { name: "Comprobar cantidad", exact: true });
      const sourceUrl = new URL(await source.getAttribute("href"), origin);
      expect(sourceUrl.pathname).toBe(
        "/evidence/" + encodeURIComponent(firstRow.document_id),
      );
      expect(sourceUrl.searchParams.get("month")).toBe("2019-01-01");
      expect(sourceUrl.searchParams.get("market")).toBe(marketId);
      expect(sourceUrl.searchParams.get("food")).toBe(firstRow.food_id);
      const sourceResponse = page.waitForResponse((r) => {
        const u = new URL(r.url());
        return (
          u.pathname ===
            "/api/evidence/" + encodeURIComponent(firstRow.document_id) &&
          u.searchParams.get("month") === "2019-01-01" &&
          u.searchParams.get("food") === firstRow.food_id
        );
      });
      await source.click();
      const sourceResult = await sourceResponse;
      expect(sourceResult.status()).toBe(200);
      const evidence = await sourceResult.json();
      expect(
        evidence.records.some(
          (r) =>
            r.period_start === "2019-01-01" &&
            r.market_id === marketId &&
            Number(r.quantity_kg) === Number(firstRow.quantity_kg),
        ),
      ).toBe(true);
      await expect(page.locator(".evidence-heading h2")).toBeVisible();
      await expect(
        page.getByRole("link", { name: "Descargar archivo", exact: true }),
      ).toBeVisible();
      await captureElement(
        page.locator(".evidence-heading"),
        "26-historical-supply-source-document",
      );
      await device.shell("input keyevent 4");
      await expect(page.locator(".evidence-heading")).toHaveCount(0);
      await expect(months).toHaveValue("2019-01-01");
      const january2020 = await verifyMonth("2020-01-01");
      await captureElement(
        content.locator(".supply-summary"),
        "26-january-2020-supply-total",
      );
      await verifyMonth(availableMonths[0]);
      await expect(months).toBeEnabled();
      await expect(months).toHaveValue(availableMonths[0]);
      await expect(months.locator('option[value="2019-01-01"]')).toHaveCount(1);
      await expect(months.locator('option[value="2020-01-01"]')).toHaveCount(1);
      expect(await months.locator("option").count()).toBe(
        availableMonths.length,
      );
      await expect(filters(content)).toContainText("Mercar");
      await readableFilters(content);
      const monthControlWidth = await months.evaluate((el) => {
        const panel = el.closest("section");
        const style = getComputedStyle(panel);
        return {
          width: el.getBoundingClientRect().width,
          availableWidth:
            panel.clientWidth -
            parseFloat(style.paddingLeft) -
            parseFloat(style.paddingRight),
        };
      });
      expect(monthControlWidth.width).toBeGreaterThanOrEqual(
        monthControlWidth.availableWidth - 2,
      );
      const monthTextFit = await months.evaluate((el) => {
        const style = getComputedStyle(el);
        const measure = document.createElement("canvas").getContext("2d");
        measure.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        const text = el.selectedOptions[0].textContent;
        return {
          text,
          width: el.clientWidth,
          requiredWidth:
            measure.measureText(text).width +
            parseFloat(style.paddingLeft) +
            parseFloat(style.paddingRight) +
            24,
        };
      });
      expect(monthTextFit.width).toBeGreaterThanOrEqual(
        monthTextFit.requiredWidth,
      );
      await captureElement(
        page.getByRole("region", { name: "Filtros de abastecimiento" }),
        "26-latest-month-all-history-still-reachable",
      );
      await layout();
      return {
        availableHistoricalMonths: availableMonths.length,
        january2019: {
          totalKg: january2019.total,
          rows: january2019.data.rows.length,
        },
        january2020: {
          totalKg: january2020.total,
          rows: january2020.data.rows.length,
        },
        sourceDocumentId: firstRow.document_id,
        selectedHistoricalSourceQuantityVerified: true,
        yearlyBarLabelsAndHorizontalScroll: true,
        simplifiedMonthOnlyControls: true,
        allHistoricalMonthsRemainReachable: true,
        monthControlWidth,
        monthTextFit,
      };
    });
    await step("27-native-catalog-scroll-save-back-card-paint", async () => {
      const paintMode = process.env.ANDROID_CATALOG_PAINT_MODE || "baseline";
      const cdp = await page.context().newCDPSession(page);
      let scriptId;
      if (paintMode !== "baseline") {
        const css =
          paintMode === "contain-paint"
            ? ".product-card { contain: paint !important; }"
            : ".product-card,.product-card:hover,.product-image-link img,.product-card:hover .product-image-link img {transform:none!important;transition:none!important;}";
        const source = `(${function (css) {
          const insert = () => {
            if (!document.head) return false;
            const style = document.createElement("style");
            style.id = "android-catalog-paint-diagnostic";
            style.textContent = css;
            document.head.append(style);
            return true;
          };
          if (!insert()) {
            const observer = new MutationObserver(() => {
              if (insert()) observer.disconnect();
            });
            observer.observe(document, { childList: true, subtree: true });
          }
        }.toString()})(${JSON.stringify(css)});`;
        scriptId = (
          await cdp.send("Page.addScriptToEvaluateOnNewDocument", { source })
        ).identifier;
      }
      try {
        await navigate("/products");
        await page.getByLabel("Departamento", { exact: true }).selectOption("");
        await expect(page.locator(".product-card")).toHaveCount(24);
        const states = [];
        const inspectCards = async (label) => {
          const state = await page.evaluate(() => {
            const rect = (el) => {
              const r = el.getBoundingClientRect(),
                style = getComputedStyle(el);
              return {
                x: r.x,
                y: r.y,
                width: r.width,
                height: r.height,
                right: r.right,
                bottom: r.bottom,
                position: style.position,
                transform: style.transform,
                overflow: style.overflow,
                contain: style.contain,
                willChange: style.willChange,
              };
            };
            const hit = (el) => {
              const r = el.getBoundingClientRect(),
                x = r.x + r.width / 2,
                y = r.y + r.height / 2;
              if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight)
                return null;
              const target = document.elementFromPoint(x, y);
              return {
                x,
                y,
                tag: target?.tagName,
                owner: target
                  ?.closest(".product-card")
                  ?.querySelector(".product-name")?.textContent,
                text: target?.textContent?.slice(0, 120),
              };
            };
            return {
              scrollY,
              viewport: { width: innerWidth, height: innerHeight },
              media: {
                hover: matchMedia("(hover:hover)").matches,
                fine: matchMedia("(pointer:fine)").matches,
                coarse: matchMedia("(pointer:coarse)").matches,
              },
              cards: [...document.querySelectorAll(".product-card")].map(
                (el) => ({
                  name: el.querySelector(".product-name").textContent,
                  priceText: el.querySelector(".product-price").textContent,
                  href: el.querySelector(".product-name").getAttribute("href"),
                  card: rect(el),
                  image: rect(el.querySelector(".product-image-link")),
                  bitmap: el.querySelector("img")
                    ? rect(el.querySelector("img"))
                    : null,
                  imageHit: hit(el.querySelector(".product-image-link")),
                  priceHit: hit(el.querySelector(".product-price")),
                  body: rect(el.querySelector(".product-card-body")),
                  nameBox: rect(el.querySelector(".product-name")),
                  price: rect(el.querySelector(".product-price")),
                  footer: rect(el.querySelector(".product-card-footer")),
                }),
              ),
            };
          });
          states.push({ label, ...state });
          writeFileSync(
            `${dir}/27-card-geometry.json`,
            JSON.stringify(states, null, 2),
          );
          screenshot("27-" + label);
          if (
            ["initial-grid", "tomato-settled-after-load-more"].includes(label)
          ) {
            const bitmap = await cdp.send("Page.captureScreenshot", {
              format: "png",
              fromSurface: true,
            });
            writeFileSync(
              `${dir}/27-${label}-webview-cdp.png`,
              Buffer.from(bitmap.data, "base64"),
            );
          }
          return state;
        };
        await page
          .locator(".product-grid")
          .evaluate((el) =>
            el.scrollIntoView({ block: "start", behavior: "instant" }),
          );
        await page.waitForTimeout(200);
        await inspectCards("initial-grid");
        for (let i = 0; i < 7; i++) {
          await device.shell("input swipe 520 1990 520 670 280");
          if ([0, 2, 6].includes(i)) await inspectCards("native-down-" + i);
        }
        for (let i = 0; i < 7; i++) {
          await device.shell("input swipe 520 690 520 2010 250");
          if ([0, 3, 6].includes(i)) await inspectCards("native-up-" + i);
        }
        const first = page.locator(".product-card").first();
        await first.locator(".save-button").click();
        await inspectCards("after-save-toggle");
        const third = page.locator(".product-card").nth(2),
          link = third.locator(".product-name");
        const target = new URL(await link.getAttribute("href"), origin);
        await link.click();
        await expect(page).toHaveURL(new RegExp(target.pathname));
        await expect(page.getByTestId("current-product-price")).toBeVisible();
        await device.shell("input keyevent 4");
        await expect(page).toHaveURL(/\/products(?:\?|$)/);
        await expect(page.locator(".product-card")).toHaveCount(24);
        await page
          .locator(".product-card")
          .nth(2)
          .evaluate((el) =>
            el.scrollIntoView({ block: "start", behavior: "instant" }),
          );
        await page.waitForTimeout(350);
        await inspectCards("after-native-detail-back");
        await page.getByRole("button", { name: /^Ver más productos/ }).click();
        await expect(page.locator(".product-card")).toHaveCount(48);
        await inspectCards("48-cards-loaded");
        await page
          .locator(".product-card")
          .nth(2)
          .evaluate((el) =>
            el.scrollIntoView({ block: "start", behavior: "instant" }),
          );
        await page.waitForTimeout(350);
        await inspectCards("tomato-settled-after-load-more");
        await layout();
        const overlaps = states.flatMap((state) =>
          state.cards.flatMap((c) => {
            const bad = [];
            if (c.body.y < c.image.bottom - 1) bad.push("body overlaps image");
            for (const key of ["body", "price", "footer", "nameBox"]) {
              const part = c[key];
              if (
                part.y < c.card.y - 1 ||
                part.bottom > c.card.bottom + 1 ||
                part.x < c.card.x - 1 ||
                part.right > c.card.right + 1
              )
                bad.push(key + " escapes card");
            }
            return bad.map((problem) => ({
              state: state.label,
              name: c.name,
              problem,
            }));
          }),
        );
        writeFileSync(
          `${dir}/27-layout-overlaps.json`,
          JSON.stringify(overlaps, null, 2),
        );
        expect(overlaps).toEqual([]);
        return {
          capturedStates: states.length,
          initialCards: 24,
          expandedCards: 48,
          cardGeometryContained: true,
          nativeSwipes: 14,
          saveToggleAndNativeBack: true,
          paintMode,
          nativePaintRequiresVisualReview: true,
        };
      } finally {
        if (scriptId)
          await cdp.send("Page.removeScriptToEvaluateOnNewDocument", {
            identifier: scriptId,
          });
        await page.evaluate(() =>
          document.getElementById("android-catalog-paint-diagnostic")?.remove(),
        );
        await cdp.detach();
      }
    });
    await step(
      "28-unified-catalog-official-search-save-and-return",
      async () => {
        await navigate("/products");
        await page.getByLabel("Departamento", { exact: true }).selectOption("");
        const search = page.getByLabel("Buscar producto", { exact: true });
        const currency = page.getByLabel("Moneda", { exact: true });
        const category = page.getByLabel("Categoría", { exact: true });
        await expect(currency).toBeVisible();
        const catalog = await get("/api/catalog");
        const rows = catalog.products;
        expect(new Set(rows.map((r) => r.identity)).size).toBe(rows.length);
        const arabica = rows.find(
          (r) =>
            r.kind === "official-reference" &&
            r.source === "World Bank" &&
            fold(r.name).includes("arabica"),
        );
        const robusta = rows.find(
          (r) =>
            r.kind === "official-reference" &&
            r.source === "World Bank" &&
            fold(r.name).includes("robusta"),
        );
        const fnc = rows.find((r) => r.id === "cafe-pergamino-seco");
        const rose = rows.find(
          (r) =>
            r.category === "Flores" &&
            r.source === "USDA AMS" &&
            fold(r.name).includes("rosa"),
        );
        const colombianFlower = rows.find(
          (r) =>
            r.category === "Flores" &&
            r.source === "USDA AMS" &&
            fold(JSON.stringify(r.search_terms)).includes("colombia"),
        );
        const summaries = rows.filter((r) =>
          r.href.startsWith("/references/summary-"),
        );
        const city =
          rows.find(
            (r) =>
              r.kind === "product" &&
              r.series === "city" &&
              r.id === "limon-tahiti",
          ) || rows.find((r) => r.kind === "product" && r.series === "city");
        expect(arabica).toBeTruthy();
        expect(robusta).toBeTruthy();
        expect(fnc).toBeTruthy();
        expect(rose).toBeTruthy();
        expect(colombianFlower).toBeTruthy();
        expect(city).toBeTruthy();
        const summaryNames = [...new Set(summaries.map((row) => row.name))];
        expect(summaryNames.length).toBeGreaterThanOrEqual(13);
        await expect(
          page.locator(
            'a[href="/references"],a[href="/regional"],a[href^="/data-references"]',
          ),
        ).toHaveCount(0);
        const unitLabel = (unit) =>
          ({ "125kg": "carga de 125 kg", unit: "unidad", litre: "litro" })[
            unit
          ] || unit;
        const cardFor = (row) =>
          page.locator(
            ".product-card[data-catalog-identity=" +
              JSON.stringify(row.identity) +
              "]",
          );
        const verifyCard = async (row) => {
          const card = cardFor(row);
          await expect(card).toBeVisible();
          await expect(card.locator(".product-name")).toHaveText(row.name);
          await expect(card.locator(".product-price")).toHaveAttribute(
            "data-price",
            String(row.price),
          );
          await expect(card.locator(".product-price")).toHaveAttribute(
            "data-currency",
            row.currency,
          );
          await expect(card.locator(".product-price strong")).toHaveText(
            new Intl.NumberFormat("es-CO", {
              maximumFractionDigits:
                row.currency === "COP"
                  ? row.kind === "official-reference"
                    ? 2
                    : 0
                  : 4,
            }).format(Number(row.price)),
          );
          await expect(card.locator(".product-price")).toContainText(
            "/ " + unitLabel(row.unit),
          );
          await expect(card.locator(".product-card-body")).toContainText(
            row.basis,
          );
          await expect(card.locator(".product-date")).toContainText(
            row.date.slice(0, 4),
          );
          return card;
        };
        const query = async (text) => {
          await search.fill(text);
          await search.press("Escape");
          await expect
            .poll(() => new URL(page.url()).searchParams.get("q") || "")
            .toBe(text);
        };
        let summarySource;
        const verifyReferenceDetail = async (row, openSource = false) => {
          const card = await verifyCard(row);
          const returnTo =
            new URL(page.url()).pathname + new URL(page.url()).search;
          const href = new URL(
            await card.locator(".product-name").getAttribute("href"),
            origin,
          );
          expect(href.searchParams.get("returnTo")).toBe(returnTo);
          await card.locator(".product-name").click();
          await expect(page).toHaveURL(new RegExp(href.pathname));
          await expect(page.locator("h1")).toHaveText(row.name);
          const { reference } = await get(
            "/api/references?id=" + encodeURIComponent(row.quote_key),
          );
          expect(Number(reference.price)).toBe(Number(row.price));
          expect(reference.currency).toBe(row.currency);
          expect(reference.unit).toBe(row.unit);
          const format = new Intl.NumberFormat("es-CO", {
            style: "currency",
            currency: row.currency,
            currencyDisplay: "code",
            maximumFractionDigits: row.currency === "COP" ? 2 : 4,
          });
          await expect(page.getByTestId("current-product-price")).toHaveText(
            format.format(Number(row.price)),
          );
          await expect(page.locator(".product-price-header")).toContainText(
            "Por " + row.unit,
          );
          await expect(filters()).toContainText(row.currency);
          await expect(filters()).toContainText(row.source);
          await expect(filters()).toContainText(row.unit);
          await expect(filters()).toContainText(row.market);
          await expect(page.locator(".back-link")).toHaveAttribute(
            "href",
            returnTo,
          );
          await expect(
            page
              .locator(".product-price-header")
              .getByRole("link", { name: "Consultar fuente", exact: true }),
          ).toBeVisible();
          await readableFilters(page);
          await captureElement(
            page.locator(".product-price-header"),
            "28-reference-" + row.quote_key,
          );
          if (openSource) {
            const source = page
              .locator(".product-price-header")
              .getByRole("link", { name: "Consultar fuente", exact: true });
            const sourceUrl = new URL(
              await source.getAttribute("href"),
              origin,
            );
            expect(sourceUrl.pathname).toBe(
              "/evidence/" + encodeURIComponent(reference.document_id),
            );
            expect(sourceUrl.searchParams.get("locator")).toBe(
              reference.source_locator,
            );
            await source.click();
            await expect(page.locator(".evidence-heading h2")).toBeVisible();
            const workbook = page.getByRole("region", {
              name: "Visor de Excel de solo lectura",
            });
            await expect(workbook.locator("tbody tr").first()).toBeVisible();
            await expect(
              workbook.locator(
                "tbody input,tbody textarea,tbody [contenteditable=true]",
              ),
            ).toHaveCount(0);
            await expect(
              page.getByRole("link", {
                name: "Descargar archivo",
                exact: true,
              }),
            ).toHaveAttribute(
              "href",
              "/api/evidence/" + reference.document_id + "/content",
            );
            const locatedRow = sourceUrl.searchParams.get("row");
            if (locatedRow)
              await expect(
                workbook.locator("tbody tr").first().locator("th"),
              ).toHaveText(locatedRow);
            const locatedSheet = sourceUrl.searchParams.get("sheet");
            if (locatedSheet)
              await expect(
                workbook.getByLabel("Hoja del archivo Excel"),
              ).toHaveValue(locatedSheet);
            await captureElement(
              workbook.locator(".workbook-range"),
              "28-summary-original-excel-source-locator",
            );
            summarySource = {
              documentId: reference.document_id,
              locator: reference.source_locator,
              sheet: locatedSheet,
              row: locatedRow,
              readOnlyWorkbookRendered: true,
            };
            await device.shell("input keyevent 4");
            await expect(page.locator(".evidence-heading")).toHaveCount(0);
          }
          await device.shell("input keyevent 4");
          await expect(page).toHaveURL(origin + returnTo);
          await verifyCard(row);
          return returnTo;
        };
        await query("Café");
        await verifyCard(fnc);
        await verifyCard(arabica);
        await verifyCard(robusta);
        await currency.selectOption("USD");
        await expect(cardFor(fnc)).toHaveCount(0);
        await verifyCard(arabica);
        await verifyCard(robusta);
        expect(
          await page
            .locator(".product-card .product-price")
            .evaluateAll((nodes) =>
              nodes.every((n) => n.dataset.currency === "USD"),
            ),
        ).toBe(true);
        await expect(filters()).toContainText("USD");
        await expect(filters()).toContainText("Café");
        await expect(page.locator(".map-button")).toHaveCount(0);
        await readableFilters(page);
        await captureElement(
          page.locator(".product-grid"),
          "28-coffee-usd-arabica-robusta-main-catalog",
        );
        const coffeeCard = await verifyCard(arabica);
        if (
          (await coffeeCard
            .locator(".save-button")
            .getAttribute("aria-pressed")) !== "true"
        )
          await coffeeCard.locator(".save-button").click();
        await expect(coffeeCard.locator(".save-button")).toHaveAttribute(
          "aria-pressed",
          "true",
        );
        await expect
          .poll(async () =>
            page.evaluate(
              (key) =>
                JSON.parse(
                  localStorage.getItem("agroamigo-preferences-v2") || "{}",
                ).saved?.includes(key),
              arabica.saved_key,
            ),
          )
          .toBe(true);
        const coffeeReturnTo = await verifyReferenceDetail(arabica);
        await expect(search).toHaveValue("Café");
        await expect(currency).toHaveValue("USD");
        await page
          .locator(".results-label")
          .getByRole("link", { name: "Mis guardados", exact: true })
          .click();
        await expect(page).toHaveURL(/\/saved$/);
        await verifyCard(arabica);
        await page.reload({ waitUntil: "domcontentloaded" });
        await expect(cardFor(arabica).locator(".save-button")).toHaveAttribute(
          "aria-pressed",
          "true",
        );
        await verifyCard(arabica);
        await navigate("/products");
        await query("Rosas");
        await category.selectOption("Flores");
        await currency.selectOption("USD");
        await verifyCard(rose);
        await expect(filters()).toContainText("Flores");
        await expect(filters()).toContainText("USD");
        await expect(filters()).toContainText("Rosas");
        await captureElement(
          page.locator(".product-grid"),
          "28-roses-main-catalog",
        );
        await verifyReferenceDetail(rose);
        await expect(search).toHaveValue("Rosas");
        await expect(category).toHaveValue("Flores");
        await expect(currency).toHaveValue("USD");
        await query("Flores Colombia");
        await verifyCard(colombianFlower);
        await verifyReferenceDetail(colombianFlower);
        await navigate("/products");
        await query(city.name);
        const cityCard = await verifyCard(city);
        const cityHref = new URL(
          await cityCard.locator(".product-name").getAttribute("href"),
          origin,
        );
        expect(cityHref.searchParams.get("series")).toBe("city");
        expect(cityHref.searchParams.get("presentation")).toBe(
          city.presentation,
        );
        expect(cityHref.searchParams.get("units")).toBe(city.units);
        await cityCard.locator(".product-name").click();
        await expect(page.getByTestId("current-product-price")).toHaveText(
          money(city.price),
        );
        await expect(
          page.getByLabel("Presentación", { exact: true }),
        ).toHaveValue(city.presentation);
        await expect(page.getByLabel("Unidades", { exact: true })).toHaveValue(
          city.units,
        );
        await device.shell("input keyevent 4");
        await expect(search).toHaveValue(city.name);
        await navigate("/products");
        await query(summaries[0].name);
        await verifyReferenceDetail(summaries[0], true);
        await layout();
        return {
          catalogRows: rows.length,
          uniqueIdentities: true,
          summaryOnlyNames: summaryNames.length,
          summaryQuoteVariants: summaries.length,
          coffeeReturnTo,
          arabica: {
            price: arabica.price,
            unit: arabica.unit,
            currency: arabica.currency,
          },
          robusta: {
            price: robusta.price,
            unit: robusta.unit,
            currency: robusta.currency,
          },
          rose: {
            name: rose.name,
            price: rose.price,
            unit: rose.unit,
            currency: rose.currency,
          },
          colombianFlower: {
            name: colombianFlower.name,
            price: colombianFlower.price,
            unit: colombianFlower.unit,
            currency: colombianFlower.currency,
          },
          city: {
            name: city.name,
            price: city.price,
            presentation: city.presentation,
            units: city.units,
          },
          savedReferenceSurvivesReload: true,
          nativeBackRestoresSearchCategoryCurrency: true,
          legacyGatewayLinksRemoved: true,
          summarySource,
        };
      },
    );
    await step("29-home-autocomplete-native-taps-exact-quotes", async () => {
      const { products } = await get("/api/catalog");
      const official = products.find(
        (p) =>
          p.kind === "official-reference" &&
          p.currency === "USD" &&
          p.source === "World Bank" &&
          fold(p.name).includes("arabica"),
      );
      const city = products.find(
        (p) => p.kind === "product" && p.series === "city",
      );
      expect(official).toBeTruthy();
      expect(city).toBeTruthy();
      const visited = [];
      for (const product of [official, city]) {
        await navigate("/");
        await page
          .getByRole("combobox", { name: "Buscar un producto", exact: true })
          .fill(product.name);
        const option = page
          .getByRole("option")
          .filter({ has: page.getByText(product.name, { exact: true }) })
          .first();
        await expect(option).toBeVisible();
        // Android Back first dismisses an active soft keyboard. Close it before
        // selecting the suggestion so the later Back tests app navigation.
        const inputMethodBeforeTap = await shell("dumpsys input_method");
        const keyboardDismissedBeforeTap = /mInputShown=true/.test(inputMethodBeforeTap);
        if (keyboardDismissedBeforeTap) {
          await device.shell("input keyevent 4");
          await expect.poll(async () => /mInputShown=true/.test(await shell("dumpsys input_method"))).toBe(false);
          await expect(option).toBeVisible();
        }
        await option.scrollIntoViewIfNeeded();
        await captureElement(
          page.locator(".home-search"),
          "29-home-suggestion-" + product.kind,
        );
        const box = await option.boundingBox();
        const viewport = await page.evaluate(() => ({
          width: innerWidth,
          height: innerHeight,
        }));
        expect(box.y + box.height / 2).toBeLessThan(viewport.height);
        await device.shell(
          "uiautomator dump /data/local/tmp/agroamigo-validation.xml",
        );
        const xml = await shell("cat /data/local/tmp/agroamigo-validation.xml");
        const webview = xml.match(
          /<node\b[^>]*class="android\.webkit\.WebView"[^>]*>/,
        )?.[0];
        const bounds = webview?.match(
          /bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/,
        );
        expect(bounds).toBeTruthy();
        const scale = (Number(bounds[3]) - Number(bounds[1])) / viewport.width;
        const tap = {
          x: Math.round(Number(bounds[1]) + (box.x + box.width / 2) * scale),
          y: Math.round(Number(bounds[2]) + (box.y + box.height / 2) * scale),
        };
        await device.shell(`input tap ${tap.x} ${tap.y}`);
        const expected = new URL(product.href, origin);
        await expect(page).toHaveURL(
          (url) => url.pathname === expected.pathname,
        );
        const actual = new URL(page.url());
        for (const [key, value] of expected.searchParams)
          expect(actual.searchParams.get(key)).toBe(value);
        expect(actual.searchParams.get("returnTo")).toBe(
          "/products?q=" + encodeURIComponent(product.name),
        );
        await expect(page.locator("h1")).toHaveText(product.name);
        if (product.kind === "official-reference") {
          await expect(
            page.getByTestId("current-product-price"),
          ).toHaveAttribute("data-currency", product.currency);
          await expect(
            page.getByTestId("current-product-price"),
          ).toHaveAttribute("data-price", String(product.price));
        }
        await captureElement(
          page.locator(".product-price-header"),
          "29-home-native-tap-detail-" + product.kind,
        );
        await device.shell("input keyevent 4");
        await expect(page).toHaveURL(origin + "/");
        await expect(
          page.getByRole("combobox", {
            name: "Buscar un producto",
            exact: true,
          }),
        ).toBeVisible();
        visited.push({
          name: product.name,
          kind: product.kind,
          href: product.href,
          currency: product.currency,
          unit: product.unit,
          price: product.price,
          tap,
          keyboardDismissedBeforeTap,
        });
      }
      await device.shell("rm -f /data/local/tmp/agroamigo-validation.xml");
      return {
        actualNativeTap: true,
        exactQuoteAndCityPackageLinks: true,
        hardwareBackReturnedHome: true,
        visited,
      };
    });
    await step("30-cleansheet-table-waterfall-and-break-even", async () => {
      await navigate("/farm");
      await page.getByLabel("Buscar municipio", { exact: true }).fill("Pitalito");
      await page.getByRole("option", { name: /PITALITO.*HUILA/i }).click();
      await page.getByRole("tab", { name: /Costos y rentabilidad/ }).click();
      await expect(page.locator(".clean-workspace")).toBeVisible();
      await page.getByLabel("Área que quieres analizar (ha)", { exact: true }).fill("2");
      await page.getByLabel("Rendimiento esperado (kg/ha)", { exact: true }).fill("1000");
      await page.getByLabel("Pérdidas antes de vender (%)", { exact: true }).fill("10");
      await page.getByRole("button", { name: "Mi precio", exact: true }).click();
      await page.getByLabel("Mi precio esperado (COP/kg)").fill("2000");
      const costs=page.locator(".clean-cost-edit input");
      const amounts=[200000,300000,100000,0];
      expect(await costs.count()).toBe(4);
      for(let i=0;i<amounts.length;i++) await costs.nth(i).fill(String(amounts[i]));
      await page.getByLabel("Transporte, empaque y venta (COP totales)").fill("100000");
      await page.getByLabel("Comisión sobre la venta (%)", { exact: true }).fill("10");
      const kpis=page.locator(".clean-kpis strong");
      await expect(kpis.nth(0)).toHaveText(money(3600000));
      await expect(kpis.nth(1)).toHaveText(money(1660000));
      await expect(kpis.nth(2)).toHaveText(money(1940000));
      await expect(kpis.nth(3)).toHaveText(money(1300000/1620)+"/kg");
      await page.locator(".clean-result-heading h3").click();
      await expect(page.locator(".clean-waterfall")).toBeVisible();
      await captureElement(page.locator(".clean-results"),"30-cleansheet-waterfall");
      await page.getByRole("button", { name: "Tabla", exact: true }).click();
      await expect(page.locator(".clean-result-table tbody tr.total td").nth(1)).toHaveText(money(1940000));
      await captureElement(page.locator(".clean-table-wrap"),"30-cleansheet-table");
      await page.getByLabel("Área que quieres analizar (ha)", { exact: true }).fill("-1");
      await expect(page.locator(".clean-kpis")).toHaveCount(0);
      await expect(page.locator(".clean-results .clean-incomplete")).toContainText("área y rendimiento positivos");
      await layout();
      return {revenue:3600000,costs:1660000,profit:1940000,breakEven:1300000/1620,waterfallAndTable:true,negativeAreaRejected:true};
    });
  } finally {
    for (const [kind, state] of Object.entries(networkBefore))
      if (["0", "1"].includes(state))
        await device.shell(
          `svc ${kind} ${state === "1" ? "enable" : "disable"}`,
        );
    const networkAfter = {
      wifi: await shell("settings get global wifi_on"),
      data: await shell("settings get global mobile_data"),
    };
    const networkRestored =
      JSON.stringify(networkAfter) === JSON.stringify(networkBefore);
    let restored = false;
    try {
      await waitForNetwork();
      if (page.isClosed())
        page = await (
          await device.webView({ pkg: "co.agroamigo.demo" })
        ).page();
      await navigate("/");
      restored = await page.evaluate((state) => {
        for (const key of Object.keys(localStorage))
          if (!(key in state)) localStorage.removeItem(key);
        for (const [key, value] of Object.entries(state))
          localStorage.setItem(key, value);
        return (
          JSON.stringify(Object.entries(localStorage).sort()) ===
          JSON.stringify(Object.entries(state).sort())
        );
      }, saved);
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.locator(".product-card").first()).toBeVisible();
      restored =
        restored &&
        (await page.evaluate(
          (state) =>
            JSON.stringify(Object.entries(localStorage).sort()) ===
            JSON.stringify(Object.entries(state).sort()),
          saved,
        ));
      if (restored) unlinkSync(snapshotPath);
    } catch (e) {
      errors.push({ step: "restore-user-settings", message: e.message });
    }
    let webReleaseAfter = null;
    try {
      webReleaseAfter = await readRelease();
      if (webReleaseAfter.id !== webReleaseBefore.id)
        errors.push({
          step: "release-stability",
          message: "Deployment changed during native validation",
        });
    } catch (e) {
      errors.push({ step: "release-stability", message: e.message });
    }
    const report = {
      startedAt,
      completedAt: new Date().toISOString(),
      origin,
      release: webReleaseBefore.id,
      webReleaseBefore,
      webReleaseAfter,
      native,
      suite: baseline ? "baseline" : "full",
      selection: selection?.source || null,
      results,
      jsErrors: errors,
      localSettingsRestored: restored,
      networkSettingsRestored: networkRestored,
      networkBefore,
      networkAfter,
      apiRequests: requests,
    };
    writeFileSync(`${dir}/report.json`, JSON.stringify(report, null, 2));
    await device.close();
    if (
      results.some((r) => r.status === "failed") ||
      errors.length ||
      !restored ||
      !networkRestored
    )
      process.exitCode = 1;
    console.log(
      JSON.stringify(
        {
          passed: results.filter((r) => r.status === "passed").length,
          failed: results.filter((r) => r.status === "failed").length,
          jsErrors: errors.length,
          localSettingsRestored: restored,
          report: `${dir}/report.json`,
        },
        null,
        2,
      ),
    );
    process.exit(process.exitCode || 0);
  }
})().catch(async (e) => {
  console.error(e);
  try {
    await activeDevice?.close();
  } catch {}
  process.exit(1);
});
