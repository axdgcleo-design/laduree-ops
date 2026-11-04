import SwiftUI
import Photos

struct TimelineView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var lib: PhotoLibrary
    @Binding var mode: Mode
    @State private var selected: PHAsset?

    private var items: [PHAsset] {
        lib.assets.filter { a in
            let t = store.tags[a.localIdentifier]
            if mode == .site { return t == nil || t!.mode == .site }
            else { return t?.mode == .personal }
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                ModeBar(mode: $mode)
                let groups = groupByDay(items)
                if groups.isEmpty {
                    Text("還沒有照片").foregroundStyle(.secondary).padding(.vertical, 60)
                } else {
                    ForEach(groups, id: \.day) { g in
                        HStack {
                            Text(g.day).font(.subheadline.weight(.semibold)).foregroundStyle(.secondary)
                            Spacer()
                        }.padding(.horizontal, 12).padding(.top, 10)
                        PhotoGrid(assets: g.items) { selected = $0 }
                    }
                }
                Color.clear.frame(height: 20)
            }
            .navigationTitle("時間軸")
            .sheet(item: $selected) { a in
                ClassifySheet(asset: a, initial: store.tagging(for: a.localIdentifier))
            }
        }
    }
}

struct SearchView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var lib: PhotoLibrary
    @Binding var mode: Mode
    @State private var query = ""
    @State private var selected: PHAsset?

    private var results: [PHAsset] {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return [] }
        return lib.assets.filter { a in
            guard let t = store.tags[a.localIdentifier], t.mode == mode else { return false }
            return [t.project, t.room, t.work, t.category].contains { $0.localizedCaseInsensitiveContains(q) }
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                ModeBar(mode: $mode)
                let r = results
                if query.trimmingCharacters(in: .whitespaces).isEmpty {
                    hint("輸入關鍵字開始搜尋", sub: "例：浴室、水電、想買、發票")
                } else if r.isEmpty {
                    hint("找不到「\(query)」的照片", sub: "")
                } else {
                    HStack { Text("找到 \(r.count) 張").font(.caption).foregroundStyle(.secondary); Spacer() }
                        .padding(.horizontal, 12).padding(.top, 8)
                    PhotoGrid(assets: r) { selected = $0 }
                }
                Color.clear.frame(height: 20)
            }
            .navigationTitle("搜尋")
            .searchable(text: $query, prompt: "空間 / 工種 / 分類")
            .sheet(item: $selected) { a in
                ClassifySheet(asset: a, initial: store.tagging(for: a.localIdentifier))
            }
        }
    }

    private func hint(_ title: String, sub: String) -> some View {
        VStack(spacing: 6) {
            Image(systemName: "magnifyingglass").font(.largeTitle).foregroundStyle(.secondary)
            Text(title).foregroundStyle(.secondary)
            if !sub.isEmpty { Text(sub).font(.caption).foregroundStyle(.tertiary) }
        }.padding(.vertical, 50)
    }
}
