// Render every page of a PDF to PNG with PDFKit (built into macOS).
// qlmanage only renders the first page, so use this for multi-page scores.
//
// Usage: swift render_pdf_pages.swift <pdf> <out_dir> [scale]
// Writes <out_dir>/page1.png, page2.png, ... (scale 1.8 ≈ 1100x1425 for Letter).
import AppKit
import PDFKit

let args = CommandLine.arguments
guard args.count >= 3, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("usage: swift render_pdf_pages.swift <pdf> <out_dir> [scale]\n".data(using: .utf8)!)
    exit(2)
}
let outDir = URL(fileURLWithPath: args[2], isDirectory: true)
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
let scale = CGFloat(args.count > 3 ? Double(args[3]) ?? 1.8 : 1.8)

for i in 0..<doc.pageCount {
    guard let page = doc.page(at: i) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let image = NSImage(size: NSSize(width: bounds.width * scale, height: bounds.height * scale))
    image.lockFocus()
    NSColor.white.set()
    NSRect(origin: .zero, size: image.size).fill()
    let context = NSGraphicsContext.current!.cgContext
    context.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: context)
    image.unlockFocus()
    let png = NSBitmapImageRep(data: image.tiffRepresentation!)!.representation(using: .png, properties: [:])!
    let url = outDir.appendingPathComponent("page\(i + 1).png")
    try png.write(to: url)
    print(url.path)
}
