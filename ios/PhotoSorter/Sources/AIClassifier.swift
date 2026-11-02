import Vision
import UIKit
import Photos

struct Suggestion {
    var mode: Mode
    var room: String = ""
    var work: String = ""
    var category: String = ""
    var label: String = ""
}

// 完全本地的建議分類：
// 1. 截圖 → PhotoKit 內建旗標（最準）
// 2. 文件/收據 → Vision 文字密度 + 影像標籤
// 3. 餐飲/寵物/風景 → 生活紀錄
// 4. 其他 → 工地，並嘗試猜空間
enum AIClassifier {

    static func suggest(asset: PHAsset, image: UIImage) -> Suggestion {
        if asset.mediaSubtypes.contains(.photoScreenshot) {
            return Suggestion(mode: .personal, category: "截圖", label: "螢幕截圖")
        }
        guard let cg = image.cgImage else {
            return Suggestion(mode: .site, label: "工地照片")
        }

        var labels: [String] = []
        let classify = VNClassifyImageRequest()
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([classify])
        if let obs = classify.results as? [VNClassificationObservation] {
            labels = obs.filter { $0.hasMinimumRecall(0.4, forPrecision: 0.3) || $0.confidence > 0.25 }
                        .prefix(10).map { $0.identifier.lowercased() }
        }

        var textLines = 0
        let text = VNRecognizeTextRequest()
        text.recognitionLevel = .fast
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([text])
        if let tobs = text.results as? [VNRecognizedTextObservation] { textLines = tobs.count }

        func has(_ keys: [String]) -> Bool {
            labels.contains { l in keys.contains { l.contains($0) } }
        }

        if has(["receipt","document","paper","menu","invoice","envelope","letter","newspaper"]) || textLines >= 14 {
            return Suggestion(mode: .personal, category: "發票收據", label: "文件／收據")
        }
        if has(["food","meal","dish","dessert","drink","coffee","fruit","vegetable","restaurant","cuisine"]) {
            return Suggestion(mode: .personal, category: "生活紀錄", label: "餐飲")
        }
        if has(["cat","dog","pet","animal","bird","flower","plant","sky","sunset","sunrise","beach","landscape","mountain","cloud","tree"]) {
            return Suggestion(mode: .personal, category: "生活紀錄", label: "生活")
        }

        var room = ""
        if has(["bathroom","toilet","shower","sink","lavatory"]) { room = "浴室" }
        else if has(["kitchen","stove","oven","countertop"]) { room = "廚房" }
        else if has(["bedroom"]) { room = "臥室" }
        else if has(["living_room","living room","sofa","couch"]) { room = "客廳" }
        else if has(["balcony"]) { room = "陽台" }

        return Suggestion(mode: .site, room: room, label: room.isEmpty ? "工地照片" : room)
    }
}
