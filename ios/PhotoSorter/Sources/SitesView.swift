import SwiftUI
import Photos

struct SitesView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var lib: PhotoLibrary
    @Binding var mode: Mode
    @State private var showAdd = false
    @State private var newName = ""

    var body: some View {
        NavigationStack {
            ScrollView {
                ModeBar(mode: $mode)
                if mode == .site { siteCards } else { personalCards }
                Color.clear.frame(height: 20)
            }
            .navigationTitle("整理助手")
            .toolbar {
                if mode == .site {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button { showAdd = true } label: { Image(systemName: "plus") }
                    }
                }
            }
            .alert("新增案場", isPresented: $showAdd) {
                TextField("案場名稱", text: $newName)
                Button("取消", role: .cancel) { newName = "" }
                Button("新增") { store.addProject(newName); newName = "" }
            }
        }
    }

    // MARK: 工地案場卡

    private var siteCards: some View {
        var byProject: [String: [PHAsset]] = [:]
        var unassigned: [PHAsset] = []
        for a in lib.assets {
            let t = store.tags[a.localIdentifier]
            if let t, t.mode == .personal { continue }
            if let t, t.mode == .site, !t.project.isEmpty { byProject[t.project, default: []].append(a) }
            else { unassigned.append(a) }
        }
        var cards: [(title: String, sub: String, items: [PHAsset], dest: String)] = []
        for p in store.projects {
            cards.append((p.name, p.client, byProject[p.name] ?? [], p.name))
        }
        // 已用到但未建立的案場名
        for (name, items) in byProject where !store.projects.contains(where: { $0.name == name }) {
            cards.append((name, "", items, name))
        }
        cards.sort { ($0.items.first?.creationDate ?? .distantPast) > ($1.items.first?.creationDate ?? .distantPast) }

        return VStack(spacing: 12) {
            ForEach(cards, id: \.title) { c in
                NavigationLink {
                    GroupGridView(title: c.title, assets: c.items, mode: .site)
                } label: {
                    CardView(title: c.title, sub: c.sub, count: c.items.count,
                             previews: Array(c.items.prefix(4)), accent: .blue)
                }.buttonStyle(.plain)
            }
            if !unassigned.isEmpty {
                NavigationLink {
                    GroupGridView(title: "未指定案場", assets: unassigned, mode: .site)
                } label: {
                    CardView(title: "未指定案場", sub: "", count: unassigned.count,
                             previews: Array(unassigned.prefix(4)), accent: .gray)
                }.buttonStyle(.plain)
            }
            if cards.isEmpty && unassigned.isEmpty { emptyHint }
        }
        .padding(.horizontal, 12).padding(.top, 8)
    }

    // MARK: 個人分類卡

    private var personalCards: some View {
        var byCat: [String: [PHAsset]] = [:]
        var uncat: [PHAsset] = []
        for a in lib.assets {
            guard let t = store.tags[a.localIdentifier], t.mode == .personal else { continue }
            if t.category.isEmpty { uncat.append(a) } else { byCat[t.category, default: []].append(a) }
        }
        var cards: [(String, [PHAsset])] = byCat.map { ($0.key, $0.value) }
        cards.sort { $0.1.count > $1.1.count }

        return VStack(spacing: 12) {
            if !uncat.isEmpty {
                NavigationLink {
                    GroupGridView(title: "未分類", assets: uncat, mode: .personal)
                } label: {
                    CardView(title: "未分類", sub: "", count: uncat.count,
                             previews: Array(uncat.prefix(4)), accent: .gray)
                }.buttonStyle(.plain)
            }
            ForEach(cards, id: \.0) { c in
                NavigationLink {
                    GroupGridView(title: c.0, assets: c.1, mode: .personal)
                } label: {
                    CardView(title: c.0, sub: "", count: c.1.count,
                             previews: Array(c.1.prefix(4)), accent: .green)
                }.buttonStyle(.plain)
            }
            if cards.isEmpty && uncat.isEmpty {
                VStack(spacing: 8) {
                    emptyHint
                    Text("到「整理」用 AI 把截圖、收據、生活照挑出來").font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.horizontal, 12).padding(.top, 8)
    }

    private var emptyHint: some View {
        VStack(spacing: 6) {
            Image(systemName: "photo.stack").font(.largeTitle).foregroundStyle(.secondary)
            Text(mode == .site ? "還沒有工地照片" : "還沒有個人照片").foregroundStyle(.secondary)
        }.padding(.vertical, 40)
    }
}

struct CardView: View {
    let title: String
    let sub: String
    let count: Int
    let previews: [PHAsset]
    let accent: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title).font(.headline).foregroundStyle(.primary)
                Spacer()
                Image(systemName: "chevron.right").font(.footnote).foregroundStyle(.tertiary)
            }
            Text("\(sub.isEmpty ? "" : sub + " · ")共 \(count) 張")
                .font(.caption).foregroundStyle(.secondary)
            if !previews.isEmpty {
                HStack(spacing: 4) {
                    ForEach(previews, id: \.localIdentifier) { a in
                        SquareThumb(asset: a).frame(maxWidth: .infinity)
                    }
                    ForEach(0..<max(0, 4 - previews.count), id: \.self) { _ in
                        Color.clear.frame(maxWidth: .infinity).aspectRatio(1, contentMode: .fit)
                    }
                }
            }
        }
        .padding(12)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(accent.opacity(0.5), lineWidth: 0).padding(0))
        .overlay(alignment: .leading) {
            RoundedRectangle(cornerRadius: 2).fill(accent).frame(width: 4).padding(.vertical, 10)
        }
        .shadow(color: .black.opacity(0.06), radius: 4, y: 1)
    }
}

// 案場/分類內的照片：照片 / 依工種（或依標籤）
struct GroupGridView: View {
    let title: String
    let assets: [PHAsset]
    let mode: Mode
    @EnvironmentObject var store: Store
    @State private var byType = false
    @State private var selected: PHAsset?

    var body: some View {
        ScrollView {
            if mode == .site {
                Picker("", selection: $byType) {
                    Text("照片").tag(false)
                    Text("依工種").tag(true)
                }
                .pickerStyle(.segmented).padding(.horizontal, 12).padding(.top, 8)
            }
            if byType && mode == .site {
                ForEach(worktypeSections, id: \.name) { sec in
                    HStack {
                        Text(sec.name).font(.headline)
                        Spacer()
                        Text("\(sec.items.count) 張").font(.caption).foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 12).padding(.top, 10)
                    PhotoGrid(assets: sec.items) { selected = $0 }
                }
            } else {
                PhotoGrid(assets: assets) { selected = $0 }
                    .padding(.top, 8)
            }
            Color.clear.frame(height: 20)
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $selected) { a in
            ClassifySheet(asset: a, initial: store.tagging(for: a.localIdentifier))
        }
    }

    private var worktypeSections: [(name: String, items: [PHAsset])] {
        var map: [String: [PHAsset]] = [:]
        for a in assets {
            let key = store.tags[a.localIdentifier]?.workList.first ?? ""
            map[key, default: []].append(a)
        }
        var out: [(String, [PHAsset])] = []
        for w in DEFAULT_WORK where map[w] != nil { out.append((w, map[w]!)) }
        for (k, v) in map where !k.isEmpty && !DEFAULT_WORK.contains(k) { out.append((k, v)) }
        if let none = map[""] { out.append(("未分類", none)) }
        return out.map { (name: $0.0, items: $0.1) }
    }
}
