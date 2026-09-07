import Link from "next/link";
import { IoLogoAndroid, IoDownloadOutline } from "react-icons/io5";
export default function Android() {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">TU COMPAÑERO EN EL CELULAR</span>
          <h1>AgroAmigo para Android</h1>
          <p>Tu finca, tus cuentas y tus fuentes, en la misma aplicación.</p>
        </div>
      </div>
      <section className="panel">
        <IoLogoAndroid size={48} color="#22643f" />
        <h2>Instala la versión de demostración</h2>
        <p>
          Compatible con Android 10 o posterior. Necesitas conexión a internet y
          Android System WebView actualizado para consultar datos y documentos.
          Las ofertas, el perfil y los escenarios se guardan en el dispositivo.
        </p>
        <a
          className="button primary"
          href="/downloads/agroamigo-demo.apk"
          download
        >
          <IoDownloadOutline /> Descargar APK de AgroAmigo
        </a>
        <ol>
          <li>Descarga el archivo desde tu teléfono Android.</li>
          <li>
            Ábrelo desde Descargas. Si Android lo solicita, permite a tu
            navegador instalar esta aplicación.
          </li>
          <li>
            Abre AgroAmigo y configura Mi finca, o explora el ejemplo de
            Pitalito.
          </li>
        </ol>
        <p className="privacy-note">
          Versión 1.0 demo, firmada para pruebas. Distribución directa; todavía
          no está publicada en Google Play. El perfil del navegador y el de la
          app se guardan por separado.
        </p>
        <Link className="evidence-link" href="/farm">
          Seguir usando la versión web →
        </Link>
      </section>
    </>
  );
}
