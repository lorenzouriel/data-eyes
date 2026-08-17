import type { JSX } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Login from "./pages/Login";
import MainPage from "./pages/MainPage";
import InstanceDetail from "./pages/InstanceDetail";
import DatabaseDrillDown from "./pages/DatabaseDrillDown";

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const { username, loading } = useAuth();
  if (loading) return <div className="page-loading">Loading…</div>;
  if (!username) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MainPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/instances/:instanceName"
            element={
              <ProtectedRoute>
                <InstanceDetail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/instances/:instanceName/db/:databaseName/:tab?"
            element={
              <ProtectedRoute>
                <DatabaseDrillDown />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
