import Foundation
import Photos

// 讓 PHAsset 能用在 .sheet(item:) / ForEach
extension PHAsset: Identifiable {
    public var id: String { localIdentifier }
}

enum Mode: String, Codable, CaseIterable {
    case site, personal
    var label: String { self == .site ? "工地" : "個人" }
    var icon: String { self == .site ? "building.2.fill" : "person.crop.square.fill" }
}

// 每張照片的分類資料（只存 localIdentifier + 標籤，不存照片本身）
struct Tagging: Codable, Identifiable {
    var localId: String
    var mode: Mode = .site
    var project: String = ""     // 工地：案場名稱（空＝未指定）
    var room: String = ""        // 工地：空間
    var work: String = ""        // 工地：工種（逗號分隔，可複選）
    var category: String = ""    // 個人：分類（空＝未分類）
    var favorite: Bool = false
    var updatedAt: Date = Date()

    var id: String { localId }
    var classified: Bool { mode == .site ? !project.isEmpty : !category.isEmpty }

    var workList: [String] {
        work.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }
}

struct Project: Codable, Identifiable, Hashable {
    var id = UUID()
    var name: String
    var client: String = ""
}

let DEFAULT_WORK  = ["鋁作","水電","泥作","木作","油漆","磁磚","防水","保護/拆除","鋁窗","清潔"]
let DEFAULT_ROOMS = ["浴室","廚房","臥室","客廳","書房","陽台","大廳","玄關"]
let DEFAULT_CATS  = ["想買","截圖","參考靈感","發票收據","生活紀錄","其他"]

// 本地儲存：一個 JSON 檔放在 App 的 Application Support
@MainActor
final class Store: ObservableObject {
    @Published var tags: [String: Tagging] = [:]
    @Published var projects: [Project] = []

    private let url: URL

    init() {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        url = dir.appendingPathComponent("photosorter.json")
        load()
    }

    private struct Blob: Codable { var tags: [Tagging]; var projects: [Project] }

    func load() {
        guard let data = try? Data(contentsOf: url),
              let blob = try? JSONDecoder().decode(Blob.self, from: data) else { return }
        tags = Dictionary(blob.tags.map { ($0.localId, $0) }, uniquingKeysWith: { a, _ in a })
        projects = blob.projects
    }

    func save() {
        let blob = Blob(tags: Array(tags.values), projects: projects)
        if let data = try? JSONEncoder().encode(blob) { try? data.write(to: url, options: .atomic) }
    }

    func tagging(for id: String) -> Tagging { tags[id] ?? Tagging(localId: id) }

    func update(_ t: Tagging) {
        var t = t; t.updatedAt = Date()
        tags[t.localId] = t
        save()
    }

    func remove(_ id: String) { tags[id] = nil; save() }

    @discardableResult
    func addProject(_ name: String, client: String = "") -> Bool {
        let n = name.trimmingCharacters(in: .whitespaces)
        guard !n.isEmpty, !projects.contains(where: { $0.name == n }) else { return false }
        projects.append(Project(name: n, client: client)); save()
        return true
    }

    // 個人分類：預設 + 已用過
    var personalCategories: [String] {
        let used = Set(tags.values.filter { $0.mode == .personal && !$0.category.isEmpty }.map { $0.category })
        var out = DEFAULT_CATS
        for u in used.sorted() where !out.contains(u) { out.append(u) }
        return out
    }
}
