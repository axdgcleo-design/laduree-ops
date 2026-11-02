import SwiftUI
import Photos

struct RootView: View {
    @EnvironmentObject var lib: PhotoLibrary

    var body: some View {
        Group {
            switch lib.status {
            case .authorized, .limited:
                TabsView()
            default:
                PermissionView()
            }
        }
        .onAppear {
            if lib.status == .authorized || lib.status == .limited {
                if lib.assets.isEmpty { lib.load() }
            }
        }
    }
}

struct PermissionView: View {
    @EnvironmentObject var lib: PhotoLibrary
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "photo.on.rectangle.angled").font(.system(size: 54)).foregroundStyle(.secondary)
            Text("照片整理助手").font(.title.bold())
            Text("讀取你的相簿，依案場 / 工種與個人分類整理。\n照片不會離開你的手機。")
                .multilineTextAlignment(.center).foregroundStyle(.secondary).font(.subheadline)
            Button {
                lib.requestAndLoad()
            } label: {
                Text("讀取相簿").bold().frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent).controlSize(.large)
            .padding(.horizontal, 40).padding(.top, 8)
            if lib.status == .denied || lib.status == .restricted {
                Text("相簿權限被關閉，請到「設定 › 照片」開啟。")
                    .font(.caption).foregroundStyle(.orange)
            }
        }
        .padding()
    }
}

struct TabsView: View {
    @State private var mode: Mode = .site

    var body: some View {
        TabView {
            SitesView(mode: $mode)
                .tabItem { Label("案場", systemImage: "building.2") }
            TimelineView(mode: $mode)
                .tabItem { Label("時間軸", systemImage: "clock") }
            OrganizeView(mode: $mode)
                .tabItem { Label("整理", systemImage: "tray.full") }
            SearchView(mode: $mode)
                .tabItem { Label("搜尋", systemImage: "magnifyingglass") }
        }
    }
}

// 依日期分組
func groupByDay(_ assets: [PHAsset]) -> [(day: String, items: [PHAsset])] {
    let fmt = DateFormatter(); fmt.dateFormat = "yyyy-MM-dd"
    var order: [String] = []
    var map: [String: [PHAsset]] = [:]
    for a in assets {
        let key = a.creationDate.map { fmt.string(from: $0) } ?? "未知日期"
        if map[key] == nil { order.append(key) }
        map[key, default: []].append(a)
    }
    return order.map { ($0, map[$0] ?? []) }
}
