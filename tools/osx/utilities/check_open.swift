import AppKit
import ApplicationServices
import Foundation

// Detects whether a file is currently open in another process.
//
// Usage:
//   check_open <file_path>          -> prints TRUE or FALSE
//   check_open --check-permission   -> prints GRANTED or DENIED (never prompts)
//   check_open --request-permission -> prints GRANTED or DENIED (shows the
//                                      system Accessibility dialog if needed)
//
// Detection runs in tiers. Tier 1 (lsof) needs no special privilege. Tiers 2-4
// read window/tab titles through the Accessibility API, which requires the user
// to grant Accessibility permission. When that permission is missing the GUI
// tiers are skipped rather than failing, so the answer degrades to the kernel
// check instead of being wrong.

// MARK: - Accessibility permission

// Literal value of kAXTrustedCheckOptionPrompt. Used directly because the
// constant is imported as Unmanaged<CFString> on some SDK versions.
let axPromptOptionKey = "AXTrustedCheckOptionPrompt"

func hasAccessibilityPermission(prompt: Bool) -> Bool {
    let options = [axPromptOptionKey: prompt] as CFDictionary
    return AXIsProcessTrustedWithOptions(options)
}

// MARK: - Validation & Setup

guard CommandLine.arguments.count > 1 else {
    fputs("Usage: ./check_open <file_path>\n", stderr)
    exit(1)
}

let firstArgument = CommandLine.arguments[1]

if firstArgument == "--check-permission" || firstArgument == "--request-permission" {
    let prompt = firstArgument == "--request-permission"
    print(hasAccessibilityPermission(prompt: prompt) ? "GRANTED" : "DENIED")
    exit(0)
}

let targetPath = URL(fileURLWithPath: firstArgument).standardizedFileURL.path
let targetURL = URL(fileURLWithPath: targetPath)
let filename = targetURL.lastPathComponent

// Blacklist apps whose window/tab titles represent commands, folders, or URLs
let titleInspectionBlacklist: Set<String> = [
    "com.apple.Terminal",
    "com.googlecode.iterm2",
    "net.kovidgoyal.kitty",
    "io.alacritty",
    "com.mitchellh.ghostty",
    "com.apple.finder",
    "com.apple.Safari",
    "com.google.Chrome",
    "org.mozilla.firefox",
    "com.apple.ActivityMonitor"
]

// MARK: - Helper Functions

func titleMatches(title: String, token: String) -> Bool {
    guard !token.isEmpty && title.localizedCaseInsensitiveContains(token) else { return false }
    let pattern = "(^|[\\s/●*•—–\\-\\[\\](])" + NSRegularExpression.escapedPattern(for: token) + "([\\s—–\\-\\[\\])]|$)"
    return title.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil
}

func findTabTitles(in element: AXUIElement, maxDepth: Int = 3) -> [String] {
    guard maxDepth > 0 else { return [] }
    var titles: [String] = []
    var childrenRef: CFTypeRef?

    if AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &childrenRef) == .success,
       let children = childrenRef as? [AXUIElement] {
        for child in children {
            var roleRef: CFTypeRef?
            AXUIElementCopyAttributeValue(child, kAXRoleAttribute as CFString, &roleRef)
            let role = roleRef as? String ?? ""

            if role == "AXRadioButton" || role == "AXTab" || role == "AXTabButton" {
                var titleRef: CFTypeRef?
                if AXUIElementCopyAttributeValue(child, kAXTitleAttribute as CFString, &titleRef) == .success,
                   let title = titleRef as? String, !title.isEmpty {
                    titles.append(title)
                }
            } else {
                titles.append(contentsOf: findTabTitles(in: child, maxDepth: maxDepth - 1))
            }
        }
    }
    return titles
}

// MARK: - Tier 1: Kernel POSIX Check (lsof)

func isKernelOpen(target: String) -> Bool {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
    task.arguments = ["-F", "pn", target]

    let pipe = Pipe()
    task.standardOutput = pipe
    task.standardError = Pipe()

    do { try task.run() } catch { return false }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    task.waitUntilExit()

    guard let output = String(data: data, encoding: .utf8) else { return false }

    // The caller (Drive) reads xattrs and digests on the same file moments
    // before asking, so its own descriptors must not count as "in use".
    let ownPids: Set<pid_t> = [getpid(), getppid()]
    var currentPidFound: pid_t = 0

    for line in output.split(separator: "\n") {
        guard let prefix = line.first else { continue }
        let val = String(line.dropFirst())
        if prefix == "p" {
            currentPidFound = pid_t(val) ?? 0
        } else if prefix == "n" {
            if !ownPids.contains(currentPidFound) {
                let norm = URL(fileURLWithPath: val).standardizedFileURL.path
                if norm == target { return true }
            }
        }
    }
    return false
}

// MARK: - Tiers 2–4: GUI & Accessibility Check

func isGUIOpen(target: String, filename: String) -> Bool {
    let currentPid = getpid()
    let parentPid = getppid()

    let runningApps = NSWorkspace.shared.runningApplications.filter {
        $0.activationPolicy == .regular &&
        $0.processIdentifier != currentPid &&
        $0.processIdentifier != parentPid
    }

    for app in runningApps {
        let bundleId = app.bundleIdentifier ?? ""
        let appRef = AXUIElementCreateApplication(app.processIdentifier)
        var windowsRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(appRef, kAXWindowsAttribute as CFString, &windowsRef) == .success,
              let windows = windowsRef as? [AXUIElement] else { continue }

        for window in windows {
            // Tier 2: AXDocument URL (TextEdit, Preview, Xcode, Pages, etc.)
            var docRef: CFTypeRef?
            if AXUIElementCopyAttributeValue(window, "AXDocument" as CFString, &docRef) == .success,
               let docStr = docRef as? String {
                let docPath = docStr.hasPrefix("file://") ? (URL(string: docStr)?.path ?? docStr) : docStr
                if URL(fileURLWithPath: docPath).standardizedFileURL.path == target {
                    return true
                }
            }

            if titleInspectionBlacklist.contains(bundleId) { continue }

            // Tier 3: Window Titles (NotepadNext, Qt, cross-platform editors)
            var titleRef: CFTypeRef?
            if AXUIElementCopyAttributeValue(window, kAXTitleAttribute as CFString, &titleRef) == .success,
               let windowTitle = titleRef as? String {
                if windowTitle.contains(target) || titleMatches(title: windowTitle, token: filename) {
                    return true
                }
            }

            // Tier 4: Background Tabs (VS Code, NotepadNext inactive tabs)
            for tabTitle in findTabTitles(in: window) {
                if titleMatches(title: tabTitle, token: filename) {
                    return true
                }
            }
        }
    }
    return false
}

// MARK: - Main Execution

if isKernelOpen(target: targetPath) {
    print("TRUE")
} else if hasAccessibilityPermission(prompt: false) && isGUIOpen(target: targetPath, filename: filename) {
    print("TRUE")
} else {
    print("FALSE")
}
