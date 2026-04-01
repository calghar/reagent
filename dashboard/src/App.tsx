import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import { ToastProvider } from './components/Toast'
import AssetOverview from './pages/AssetOverview'
import AssetDetail from './pages/AssetDetail'
import EvalTrends from './pages/EvalTrends'
import CostMonitor from './pages/CostMonitor'
import InstinctStore from './pages/InstinctStore'
import ProviderConfig from './pages/ProviderConfig'
import LoopControl from './pages/LoopControl'

export default function App() {
  return (
    <ToastProvider>
      <div className="layout">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Navigate to="/assets" replace />} />
            <Route path="/assets/detail/*" element={<AssetDetail />} />
            <Route path="/assets" element={<AssetOverview />} />
            <Route path="/evals" element={<EvalTrends />} />
            <Route path="/costs" element={<CostMonitor />} />
            <Route path="/instincts" element={<InstinctStore />} />
            <Route path="/providers" element={<ProviderConfig />} />
            <Route path="/loops" element={<LoopControl />} />
          </Routes>
        </main>
      </div>
    </ToastProvider>
  )
}
