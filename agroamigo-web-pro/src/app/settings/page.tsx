'use client';

import React from 'react';
import { useSettings } from '@/context/SettingsContext';
import { useLanguage } from '@/context/LanguageContext';

export default function SettingsPage() {
  const { settings, updateChartSettings } = useSettings();
  const { locale, setLocale, t } = useLanguage();

  return (
    <div className="vstack" style={{ gap: 16, maxWidth: 720 }}>
      <section className="card">
        <h2>{t.nav_settings || 'Ajustes'}</h2>

        <div className="vstack" style={{ gap: 16, marginTop: 8 }}>
          <Row label="Idioma / Language">
            <div style={{ display: 'flex', gap: 8 }}>
              <button className={`chip ${locale === 'es' ? 'active' : ''}`} onClick={() => setLocale('es')}>Español</button>
              <button className={`chip ${locale === 'en' ? 'active' : ''}`} onClick={() => setLocale('en')}>English</button>
            </div>
          </Row>

          <Row label="Opciones de gráfico">
            <div className="vstack" style={{ gap: 8 }}>
              {([
                ['showAvgLine', 'Línea promedio'],
                ['showTrendLine', 'Línea de tendencia'],
                ['showMinMaxCallouts', 'Resaltar mín/máx'],
                ['showInteractiveCallout', 'Tooltip interactivo'],
              ] as const).map(([key, label]) => (
                <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={(settings.chart as any)[key]}
                    onChange={e => updateChartSettings({ [key]: e.target.checked })}
                  />
                  {label}
                </label>
              ))}
            </div>
          </Row>
        </div>
      </section>

      <section className="card">
        <h2>Acerca de</h2>
        <p className="muted" style={{ fontSize: 13, lineHeight: 1.6 }}>
          AgroAmigo Pro es la vista de escritorio de AgroAmigo. Datos de precios y abastecimiento
          provienen del DANE (SIPSA) con actualización continua. Esta vista está diseñada
          para analistas y profesionales; para uso en campo consulte la app móvil.
        </p>
      </section>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  );
}
