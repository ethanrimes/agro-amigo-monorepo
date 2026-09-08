package co.agroamigo.demo;

import android.Manifest;
import android.content.pm.PackageManager;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.*;
import android.widget.*;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** A small Android client for the shared Azure app. No account or private-data server sync. */
public class MainActivity extends Activity {
    private static final String ORIGIN = "https://agroamigo-demo-9a04.azurewebsites.net";
    private static final int SAVE_SCENARIO = 10;
    private WebView web;
    private ProgressBar progress;
    private LinearLayout error;
    private String pendingExport;
    private String lastPage = ORIGIN + "/";
    private boolean failed;
    private static final int LOCATION_PERMISSION = 20;
    private GeolocationPermissions.Callback pendingLocation;
    private String pendingLocationOrigin;

    private boolean trusted(String url) {
        if (url == null) return false;
        Uri uri = Uri.parse(url);
        return "https".equals(uri.getScheme()) && "agroamigo-demo-9a04.azurewebsites.net".equals(uri.getHost()) && (uri.getPort() == -1 || uri.getPort() == 443) && uri.getUserInfo() == null;
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(Color.rgb(247,248,242));
        root.setOnApplyWindowInsetsListener((v,insets)->{if(Build.VERSION.SDK_INT<30){v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets.consumeSystemWindowInsets();}android.graphics.Insets b=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout()|WindowInsets.Type.ime());v.setPadding(b.left,b.top,b.right,b.bottom);return WindowInsets.CONSUMED;});
        progress = new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal); root.addView(progress,new LinearLayout.LayoutParams(-1,6));
        FrameLayout body = new FrameLayout(this); root.addView(body,new LinearLayout.LayoutParams(-1,0,1));
        web = new WebView(this); body.addView(web,new FrameLayout.LayoutParams(-1,-1));
        error = new LinearLayout(this); error.setOrientation(LinearLayout.VERTICAL); error.setGravity(Gravity.CENTER); error.setPadding(36,36,36,36); error.setBackgroundColor(Color.rgb(247,248,242));
        TextView title = new TextView(this); title.setText("Volvamos a conectar"); title.setTextSize(26); title.setTextColor(Color.rgb(23,76,53)); error.addView(title);
        TextView message = new TextView(this); message.setText("Revisa tu conexión a internet y vuelve a intentar. Los datos que guardaste en este dispositivo se conservan."); message.setTextSize(17); message.setPadding(0,24,0,28); error.addView(message);
        Button retry = new Button(this); retry.setText("Volver a intentar"); retry.setOnClickListener(v->web.loadUrl(lastPage)); error.addView(retry); body.addView(error,new FrameLayout.LayoutParams(-1,-1)); error.setVisibility(View.GONE);
        setContentView(root);
        WebSettings settings = web.getSettings(); settings.setJavaScriptEnabled(true); settings.setDomStorageEnabled(true); settings.setAllowFileAccess(false); settings.setAllowContentAccess(false); settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW); settings.setGeolocationEnabled(true); settings.setSafeBrowsingEnabled(true); settings.setSupportMultipleWindows(false); settings.setUserAgentString(settings.getUserAgentString()+" AgroAmigoAndroid/1.0");
        settings.setSupportZoom(false); settings.setBuiltInZoomControls(false); settings.setDisplayZoomControls(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        web.setWebChromeClient(new WebChromeClient(){
            @Override public void onProgressChanged(WebView view,int value){progress.setProgress(value);progress.setVisibility(value==100?View.GONE:View.VISIBLE);}
            @Override public void onGeolocationPermissionsShowPrompt(String origin,GeolocationPermissions.Callback callback){
                if(!trusted(origin)||!trusted(web.getUrl())){callback.invoke(origin,false,false);return;}
                if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED){callback.invoke(origin,true,false);return;}
                if(pendingLocation!=null)pendingLocation.invoke(pendingLocationOrigin,false,false);
                pendingLocation=callback;pendingLocationOrigin=origin;
                requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION},LOCATION_PERMISSION);
            }
            @Override public void onGeolocationPermissionsHidePrompt(){pendingLocation=null;pendingLocationOrigin=null;}
        });
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request) {
                String url=request.getUrl().toString();
                if (trusted(url)) return false;
                if ("agroamigo-export".equals(request.getUrl().getScheme()) && request.isForMainFrame() && trusted(view.getUrl())) { saveScenario(request.getUrl()); return true; }
                if (request.isForMainFrame()) openExternal(request.getUrl());
                return true;
            }
            @Override public void onPageStarted(WebView view,String url,android.graphics.Bitmap icon){if(trusted(url)){lastPage=url;failed=false;error.setVisibility(View.GONE);}else{view.stopLoading();}}
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError reason){if(request.isForMainFrame()){failed=true;error.setVisibility(View.VISIBLE);}}
            @Override public void onReceivedHttpError(WebView view,WebResourceRequest request,WebResourceResponse response){if(request.isForMainFrame()&&response.getStatusCode()>=400){failed=true;error.setVisibility(View.VISIBLE);}}
            @Override public void onPageFinished(WebView view,String url){if(!failed)error.setVisibility(View.GONE);}
        });
        web.setDownloadListener((url,ua,disposition,mime,length)->{
            if(!trusted(url)){openExternal(Uri.parse(url));return;}
            if(!Uri.parse(url).getPath().matches("/api/evidence/[a-z0-9-]+/content")){Toast.makeText(this,"Este archivo no está disponible para descargar.",Toast.LENGTH_LONG).show();return;}
            try {String filename=URLUtil.guessFileName(url,disposition,mime);DownloadManager.Request req=new DownloadManager.Request(Uri.parse(url));req.setTitle(filename);req.setMimeType(mime);req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,filename);((DownloadManager)getSystemService(DOWNLOAD_SERVICE)).enqueue(req);Toast.makeText(this,"Descargando a la carpeta Descargas",Toast.LENGTH_LONG).show();}catch(Exception ex){Toast.makeText(this,"No se pudo iniciar la descarga.",Toast.LENGTH_LONG).show();}
        });
        if(Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,this::navigateBack);
        if(state==null || web.restoreState(state)==null)web.loadUrl(ORIGIN+"/");
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){
        super.onRequestPermissionsResult(request,permissions,results);
        if(request==LOCATION_PERMISSION&&pendingLocation!=null){boolean granted=false;for(int r:results)if(r==PackageManager.PERMISSION_GRANTED)granted=true;pendingLocation.invoke(pendingLocationOrigin,granted&&trusted(web.getUrl()),false);pendingLocation=null;pendingLocationOrigin=null;}
    }
    private void openExternal(Uri uri){String scheme=uri.getScheme();if(!"https".equals(scheme)&&!"http".equals(scheme)&&!"mailto".equals(scheme)&&!"tel".equals(scheme))return;try{startActivity(new Intent(Intent.ACTION_VIEW,uri));}catch(Exception ignored){Toast.makeText(this,"No hay una aplicación para abrir este enlace.",Toast.LENGTH_LONG).show();}}
    private void saveScenario(Uri uri){try{String json=uri.getQueryParameter("data");if(json==null||json.length()>250000||!"scenario".equals(uri.getHost()))return;new JSONObject(json);pendingExport=json;Intent save=new Intent(Intent.ACTION_CREATE_DOCUMENT);save.addCategory(Intent.CATEGORY_OPENABLE);save.setType("application/json");save.putExtra(Intent.EXTRA_TITLE,"escenario-agroamigo.json");startActivityForResult(save,SAVE_SCENARIO);}catch(Exception ex){Toast.makeText(this,"No se pudo preparar el archivo.",Toast.LENGTH_LONG).show();}}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==SAVE_SCENARIO){if(result==RESULT_OK&&data!=null&&data.getData()!=null&&pendingExport!=null){try(OutputStream out=getContentResolver().openOutputStream(data.getData())){out.write(pendingExport.getBytes(StandardCharsets.UTF_8));Toast.makeText(this,"Escenario guardado",Toast.LENGTH_LONG).show();}catch(Exception ex){Toast.makeText(this,"No se pudo guardar el archivo.",Toast.LENGTH_LONG).show();}}pendingExport=null;}}
    private void navigateBack(){if(error.getVisibility()==View.VISIBLE){error.setVisibility(View.GONE);web.loadUrl(ORIGIN+"/");}else if(web.canGoBack())web.goBack();else finish();}
    @Override public void onBackPressed(){navigateBack();}
    @Override protected void onSaveInstanceState(Bundle state){web.saveState(state);super.onSaveInstanceState(state);}
    @Override protected void onDestroy(){web.destroy();super.onDestroy();}
}
