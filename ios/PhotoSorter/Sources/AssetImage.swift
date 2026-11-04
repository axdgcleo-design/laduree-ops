import SwiftUI
import Photos

// 相簿縮圖：填滿所在容器，隨容器大小請求對應解析度
struct AssetImage: View {
    let asset: PHAsset
    @State private var image: UIImage?
    @State private var requestID: PHImageRequestID?

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Color(.secondarySystemBackground)
                if let image {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: geo.size.width, height: geo.size.height)
                        .clipped()
                }
            }
            .task(id: asset.localIdentifier) {
                load(side: max(geo.size.width, geo.size.height, 80))
            }
        }
    }

    private func load(side: CGFloat) {
        image = nil
        let scale = UIScreen.main.scale
        let target = CGSize(width: side * scale, height: side * scale)
        let o = PHImageRequestOptions()
        o.deliveryMode = .opportunistic
        o.resizeMode = .fast
        o.isNetworkAccessAllowed = true
        requestID = PHImageManager.default().requestImage(
            for: asset, targetSize: target, contentMode: .aspectFill, options: o
        ) { img, _ in
            if let img { DispatchQueue.main.async { self.image = img } }
        }
    }
}

// 正方形縮圖卡（含最愛星號、未分類橘點）
struct SquareThumb: View {
    let asset: PHAsset
    @EnvironmentObject var store: Store

    var body: some View {
        let t = store.tags[asset.localIdentifier]
        Color(.secondarySystemBackground)
            .aspectRatio(1, contentMode: .fit)
            .overlay(AssetImage(asset: asset))
            .overlay(alignment: .topTrailing) {
                if t?.favorite == true {
                    Image(systemName: "star.fill")
                        .font(.caption2).foregroundStyle(.yellow)
                        .padding(5).shadow(radius: 1)
                }
            }
            .overlay(alignment: .bottomLeading) {
                if t == nil || t?.classified == false {
                    Circle().fill(.orange).frame(width: 8, height: 8).padding(6)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .contentShape(Rectangle())
    }
}

// 可重複使用的照片格狀
struct PhotoGrid: View {
    let assets: [PHAsset]
    let onTap: (PHAsset) -> Void
    private let cols = [GridItem(.adaptive(minimum: 110), spacing: 6)]

    var body: some View {
        LazyVGrid(columns: cols, spacing: 6) {
            ForEach(assets, id: \.localIdentifier) { a in
                Button { onTap(a) } label: { SquareThumb(asset: a) }
                    .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
    }
}

// 工地/個人 切換列
struct ModeBar: View {
    @Binding var mode: Mode
    var body: some View {
        Picker("", selection: $mode) {
            ForEach(Mode.allCases, id: \.self) { m in
                Text("\(m.label)").tag(m)
            }
        }
        .pickerStyle(.segmented)
        .padding(.horizontal, 12)
        .padding(.top, 8)
    }
}
