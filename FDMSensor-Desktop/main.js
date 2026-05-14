const { app, BrowserWindow, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let pyProc = null;
let pyPort = null;
let pyStartTimeout = null;

const PY_START_TIMEOUT_MS = 15000; // 15 saniye içinde port gelmezse hata göster

const createPyProc = () => {
  let script = getScriptPath();
  console.log("Starting python server from:", script);
  
  // Try to spawn the executable
  try {
    pyProc = spawn(script, []);
  } catch (err) {
    console.error("Failed to start python server:", err);
    dialog.showErrorBox("Başlatma Hatası", "Python arka plan servisi başlatılamadı: " + err.message);
    return;
  }

  if (pyProc != null) {
    console.log('child process success');

    // Timeout: Python PORT çıktısı gelmezse hata göster
    pyStartTimeout = setTimeout(() => {
      if (!pyPort) {
        console.error("Python server did not report port within timeout.");
        dialog.showErrorBox(
          "Başlatma Zaman Aşımı",
          "Python arka plan servisi 15 saniye içinde yanıt vermedi.\nUygulama kapatılıyor."
        );
        app.quit();
      }
    }, PY_START_TIMEOUT_MS);

    // Read the port from stdout
    pyProc.stdout.on('data', (data) => {
      const output = data.toString();
      console.log('python stdout:', output);
      const match = output.match(/PORT:(\d+)/);
      if (match && !pyPort) {
        pyPort = parseInt(match[1]);
        if (pyStartTimeout) clearTimeout(pyStartTimeout);
        console.log('Python server running on port:', pyPort);
        createWindow(); // Open window only after we know the port
      }
    });

    pyProc.stderr.on('data', (data) => {
      console.error('python stderr:', data.toString());
    });
    
    pyProc.on('exit', (code) => {
      console.log(`Python process exited with code ${code}`);
      if (pyStartTimeout) clearTimeout(pyStartTimeout);
      pyProc = null;
      // Eğer pencere açılmamışsa kullanıcıya hata göster
      if (!pyPort && code !== 0 && code !== null) {
        dialog.showErrorBox(
          "Servis Hatası",
          `Python servisi beklenmedik şekilde kapandı (kod: ${code}).\nUygulama yeniden başlatın.`
        );
      }
    });
  }
}

const getScriptPath = () => {
  // If running from packaged app
  if (app.isPackaged) {
    if (process.platform === 'win32') {
      return path.join(process.resourcesPath, 'api_server.exe');
    }
    return path.join(process.resourcesPath, 'api_server_mac');
  }
  return null;
}

const exitPyProc = () => {
  if (pyStartTimeout) clearTimeout(pyStartTimeout);
  if (pyProc) {
    console.log("Shutting down Python process...");
    pyProc.kill();
    pyProc = null;
    pyPort = null;
  }
}

app.whenReady().then(() => {
  if (app.isPackaged) {
    createPyProc();
  } else {
    // Development mode
    const pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
    pyProc = spawn(pythonExecutable, [path.join(__dirname, 'api_server.py')]);
    
    if (pyProc != null) {
      // Timeout: Dev modunda da PORT gelmezse hata göster
      pyStartTimeout = setTimeout(() => {
        if (!pyPort) {
          dialog.showErrorBox(
            "Başlatma Zaman Aşımı",
            "Python servisi (dev modu) 15 saniye içinde yanıt vermedi.\nTerminalde 'python api_server.py' çalışıyor mu?"
          );
          app.quit();
        }
      }, PY_START_TIMEOUT_MS);

      pyProc.stdout.on('data', (data) => {
        const output = data.toString();
        console.log('python stdout:', output);
        const match = output.match(/PORT:(\d+)/);
        if (match && !pyPort) {
          pyPort = parseInt(match[1]);
          if (pyStartTimeout) clearTimeout(pyStartTimeout);
          console.log('Python server running on port:', pyPort);
          createWindow();
        }
      });
      pyProc.stderr.on('data', (data) => {
        console.error('python stderr:', data.toString());
      });
      pyProc.on('exit', (code) => {
        console.log(`Python dev process exited with code ${code}`);
        if (pyStartTimeout) clearTimeout(pyStartTimeout);
        pyProc = null;
        if (!pyPort && code !== 0 && code !== null) {
          dialog.showErrorBox(
            "Servis Hatası",
            `Python servisi (dev modu) başlatılamadı (kod: ${code}).\nBağımlılıkların kurulu olduğundan emin olun.`
          );
        }
      });
    }
  }
});

function createWindow () {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    title: "Trafo Termal Yönetim",
    show: false // Don't show until ready
  });

  mainWindow.loadURL(`http://127.0.0.1:${pyPort}`);
  
  // Remove default menu for cleaner desktop look
  mainWindow.setMenu(null);

  mainWindow.once('ready-to-show', () => {
    mainWindow.maximize();
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.on('window-all-closed', () => {
  // macOS'ta Dock'tan çıkılmadıkça uygulamayı tamamen kapatmıyoruz
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// macOS: Dock ikonuna tıklanınca pencereyi yeniden aç
app.on('activate', () => {
  if (mainWindow === null && pyPort) {
    createWindow();
  }
});

app.on('will-quit', exitPyProc);
