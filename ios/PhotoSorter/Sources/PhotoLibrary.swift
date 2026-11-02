import Photos
import UIKit

@MainActor
final class PhotoLibrary: ObservableObject {
    @Published var assets: [PHAsset] = []
    @Published var status: PHAuthorizationStatus = PHPhotoLibrary.authorizationStatus(for: .readWrite)
    @Published var loading = false

    func requestAndLoad() {
        PHPhotoLibrary.requestAuthorization(for: .readWrite) { st in
            Task { @MainActor in
                self.status = st
                if st == .authorized || st == .limited { self.load() }
            }
        }
    }

    func load() {
        loading = true
        let opts = PHFetchOptions()
        opts.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        let result = PHAsset.fetchAssets(with: .image, options: opts)
        var arr: [PHAsset] = []
        arr.reserveCapacity(result.count)
        result.enumerateObjects { a, _, _ in arr.append(a) }
        assets = arr
        loading = false
    }

    // 取一張可供 AI 分析或大圖預覽的影像
    func requestImage(_ asset: PHAsset, max: CGFloat) async -> UIImage? {
        await withCheckedContinuation { cont in
            let o = PHImageRequestOptions()
            o.deliveryMode = .highQualityFormat
            o.isNetworkAccessAllowed = true
            o.isSynchronous = false
            var done = false
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: CGSize(width: max, height: max),
                contentMode: .aspectFit,
                options: o
            ) { img, _ in
                if !done { done = true; cont.resume(returning: img) }
            }
        }
    }
}
