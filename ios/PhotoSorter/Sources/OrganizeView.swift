import SwiftUI
import Photos

struct OrganizeView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var lib: PhotoLibrary
    @Binding var mode: Mode
    @State private var selected: PHAsset?
    @State private var aiBusy = false
    @State private var aiProgress = 0
    @State private var aiTotal = 0

    private var pending: [PHAsset] {
        lib.assets.filter { a in
            let t = store.tags[a.localIdentifier]
            if mode == .site {
                return t == nil || (t!.mode == .site && t!.project.isEmpty)
            } else {
                return t?.mode == .personal && (t?.category.isEmpty ?? false)
            }
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                ModeBar(mode: $mode)
                let items = pending
                if items.isEmpty {
                    VStack(spacing: 8) {
                        Image(systemName: "checkmark.seal").font(.largeTitle).foregroundStyle(.green)
                        Text("都整理好了！").foregroundStyle(.secondary)
                    }.padding(.vertical, 60)
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Circle().fill(.orange).frame(width: 8, height: 8)
                            Text("未分類").font(.headline)
                            Spacer()
                            Text("\(items.count) 張").font(.caption).foregroundStyle(.secondary)
                        }
                        Text(mode == .site
                             ? "AI 會先挑出截圖/收據/生活照移到「個人」，並建議空間；案場仍由你指定。"
                             : "點一張選擇分類；或用 AI 自動分類後再確認。")
                            .font(.caption).foregroundStyle(.secondary)
                        Button {
                            Task { await runBatch(Array(items.prefix(40))) }
                        } label: {
                            HStack {
                                Image(systemName: "sparkles")
                                Text(aiBusy ? "AI 分析中… \(aiProgress)/\(aiTotal)" : "讓 AI 建議分類（前 40 張）")
                            }.frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent).tint(.purple).disabled(aiBusy)
                    }
                    .padding(.horizontal, 12).padding(.top, 8)

                    PhotoGrid(assets: items) { selected = $0 }
                        .padding(.top, 6)
                }
                Color.clear.frame(height: 20)
            }
            .navigationTitle("整理")
            .sheet(item: $selected) { a in
                ClassifySheet(asset: a, initial: store.tagging(for: a.localIdentifier))
            }
        }
    }

    private func runBatch(_ targets: [PHAsset]) async {
        aiBusy = true; aiProgress = 0; aiTotal = targets.count
        for a in targets {
            guard let img = await lib.requestImage(a, max: 600) else { aiProgress += 1; continue }
            let s = await Task.detached(priority: .userInitiated) {
                AIClassifier.suggest(asset: a, image: img)
            }.value
            var t = store.tagging(for: a.localIdentifier)
            t.mode = s.mode
            if s.mode == .personal {
                t.category = s.category
            } else {
                if !s.room.isEmpty { t.room = s.room }
                if !s.work.isEmpty { t.work = s.work }
            }
            store.update(t)
            aiProgress += 1
        }
        aiBusy = false
    }
}
