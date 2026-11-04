import SwiftUI

@main
struct PhotoSorterApp: App {
    @StateObject private var store = Store()
    @StateObject private var lib = PhotoLibrary()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environmentObject(lib)
        }
    }
}
