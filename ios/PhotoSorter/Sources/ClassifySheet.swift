import SwiftUI
import Photos

struct ClassifySheet: View {
    let asset: PHAsset
    @EnvironmentObject var store: Store
    @EnvironmentObject var lib: PhotoLibrary
    @Environment(\.dismiss) private var dismiss

    @State private var t: Tagging
    @State private var preview: UIImage?
    @State private var aiBusy = false
    @State private var aiHint = ""

    init(asset: PHAsset, initial: Tagging) {
        self.asset = asset
        _t = State(initialValue: initial)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    ZStack {
                        Color(.secondarySystemBackground)
                        if let preview {
                            Image(uiImage: preview).resizable().scaledToFit()
                        }
                    }
                    .frame(height: 220)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .listRowInsets(EdgeInsets())
                }

                Picker("類型", selection: $t.mode) {
                    ForEach(Mode.allCases, id: \.self) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)

                if t.mode == .site {
                    Section("案場") {
                        Picker("案場", selection: $t.project) {
                            Text("未指定").tag("")
                            ForEach(store.projects) { Text($0.name).tag($0.name) }
                        }
                    }
                    Section("空間") {
                        ChipPicker(options: DEFAULT_ROOMS, selection: $t.room, allowCustom: true, title: "空間")
                    }
                    Section("工種（可複選）") {
                        MultiChipPicker(options: DEFAULT_WORK, csv: $t.work)
                    }
                } else {
                    Section("分類") {
                        ChipPicker(options: store.personalCategories, selection: $t.category, allowCustom: true, title: "分類")
                    }
                }

                Section {
                    Toggle("加入最愛", isOn: $t.favorite)
                    Button {
                        Task { await runAI() }
                    } label: {
                        HStack {
                            Image(systemName: "sparkles")
                            Text(aiBusy ? "AI 分析中…" : "AI 建議分類")
                        }
                    }
                    .disabled(aiBusy)
                    if !aiHint.isEmpty {
                        Text(aiHint).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("分類")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("儲存") { store.update(t); dismiss() }.bold()
                }
            }
            .task {
                preview = await lib.requestImage(asset, max: 900)
            }
        }
    }

    private func runAI() async {
        aiBusy = true; aiHint = ""
        let img = preview ?? (await lib.requestImage(asset, max: 600))
        guard let img else { aiBusy = false; aiHint = "無法載入照片"; return }
        let s = await Task.detached(priority: .userInitiated) {
            AIClassifier.suggest(asset: asset, image: img)
        }.value
        t.mode = s.mode
        if s.mode == .site {
            if !s.room.isEmpty { t.room = s.room }
            if !s.work.isEmpty { t.work = s.work }
        } else {
            if !s.category.isEmpty { t.category = s.category }
        }
        aiHint = s.label.isEmpty ? "AI 已建議，請確認後儲存" : "AI 判斷：\(s.label)（可修改）"
        aiBusy = false
    }
}

// 單選 chip（可自訂）
struct ChipPicker: View {
    let options: [String]
    @Binding var selection: String
    var allowCustom: Bool = false
    var title: String = ""
    @State private var custom = ""

    private let cols = [GridItem(.adaptive(minimum: 72), spacing: 8)]

    var body: some View {
        LazyVGrid(columns: cols, spacing: 8) {
            ForEach(options, id: \.self) { opt in
                chip(opt, on: selection == opt) { selection = (selection == opt ? "" : opt) }
            }
        }
        if allowCustom {
            HStack {
                TextField("自訂\(title)", text: $custom)
                Button("設定") {
                    let v = custom.trimmingCharacters(in: .whitespaces)
                    if !v.isEmpty { selection = v; custom = "" }
                }.disabled(custom.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !selection.isEmpty && !options.contains(selection) {
                Text("目前：\(selection)").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func chip(_ text: String, on: Bool, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(text).font(.subheadline).lineLimit(1)
                .padding(.vertical, 6).padding(.horizontal, 10)
                .frame(maxWidth: .infinity)
                .background(on ? Color.accentColor : Color(.secondarySystemBackground))
                .foregroundStyle(on ? .white : .primary)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}

// 多選 chip，存成逗號字串
struct MultiChipPicker: View {
    let options: [String]
    @Binding var csv: String
    private let cols = [GridItem(.adaptive(minimum: 72), spacing: 8)]

    private var selected: Set<String> {
        Set(csv.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) })
    }

    var body: some View {
        LazyVGrid(columns: cols, spacing: 8) {
            ForEach(options, id: \.self) { opt in
                let on = selected.contains(opt)
                Button { toggle(opt) } label: {
                    Text(opt).font(.subheadline).lineLimit(1)
                        .padding(.vertical, 6).padding(.horizontal, 10)
                        .frame(maxWidth: .infinity)
                        .background(on ? Color.accentColor : Color(.secondarySystemBackground))
                        .foregroundStyle(on ? .white : .primary)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func toggle(_ opt: String) {
        var s = selected
        if s.contains(opt) { s.remove(opt) } else { s.insert(opt) }
        csv = options.filter { s.contains($0) }.joined(separator: ",")
    }
}
