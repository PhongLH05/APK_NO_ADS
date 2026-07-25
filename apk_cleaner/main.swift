import AppKit
import WebKit

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var process: Process?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // 1. Determine paths
        let appBundlePath = Bundle.main.bundlePath
        let pythonBin = "/usr/bin/python3"
        
        // Find gui.py in Resources or current directory
        var scriptPath = (appBundlePath as NSString).appendingPathComponent("Contents/Resources/gui.py")
        if !FileManager.default.fileExists(atPath: scriptPath) {
            scriptPath = (appBundlePath as NSString).appendingPathComponent("gui.py")
        }

        // 2. Start Python Flask server
        let p = Process()
        p.executableURL = URL(fileURLWithPath: pythonBin)
        p.arguments = [scriptPath]
        try? p.run()
        self.process = p

        // Wait briefly for server startup
        Thread.sleep(forTimeInterval: 0.8)

        // 3. Setup Native NSWindow
        let rect = NSRect(x: 0, y: 0, width: 740, height: 760)
        window = NSWindow(
            contentRect: rect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.center()
        window.title = "APK Cleaner"
        window.backgroundColor = NSColor(red: 0.05, green: 0.05, blue: 0.07, alpha: 1.0)
        window.delegate = self

        // 4. Setup WKWebView
        let config = WKWebViewConfiguration()
        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.setValue(false, forKey: "drawsBackground")
        
        if let url = URL(string: "http://127.0.0.1:5847") {
            webView.load(URLRequest(url: url))
        }
        
        window.contentView?.addSubview(webView)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func windowWillClose(_ notification: Notification) {
        process?.terminate()
        NSApp.terminate(nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        process?.terminate()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
