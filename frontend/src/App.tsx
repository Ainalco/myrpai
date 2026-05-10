import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { DndProvider } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";
import {
  Navigate,
  Route,
  BrowserRouter as Router,
  Routes,
} from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { Toaster } from "@/components/ui/toaster";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";

// Pages
import AcceptInvitePage from "@/pages/AcceptInvitePage";
import AdminModelsPage from "@/pages/AdminModelsPage";
import AdminOrgPage from "@/pages/AdminOrgPage";
import AdminPage from "@/pages/AdminPage";
import AdminRAGPage from "@/pages/AdminRAGPage";
import AdminUsagePage from "@/pages/AdminUsagePage";
import AdminUserPage from "@/pages/AdminUserPage";
import ContactOrganizationsPage from "@/pages/ContactOrganizationsPage";
import ContactPersonsPage from "@/pages/ContactPersonsPage";
import DashboardPage from "@/pages/DashboardPage";
import EmailQueuePage from "@/pages/EmailQueuePage";
import ResourcesPage from "@/pages/ResourcesPage";
import LoginPage from "@/pages/LoginPage";
import ProcessingDashboard from "@/pages/ProcessingDashboard";
import RegisterPage from "@/pages/RegisterPage";
import WorkflowDetailPage from "@/pages/WorkflowDetailPage";
import WorkflowsPage from "@/pages/WorkflowsPage";

// Settings
import SettingsAcorns from "@/components/settings/SettingsAcorns";
import SettingsAffiliate from "@/components/settings/SettingsAffiliate";
import SettingsApiKeys from "@/components/settings/SettingsApiKeys";
import SettingsAuditLog from "@/components/settings/SettingsAuditLog";
import SettingsBilling from "@/components/settings/SettingsBilling";
import SettingsIntegrations from "@/components/settings/SettingsIntegrations";
import SettingsLayout from "@/components/settings/SettingsLayout";
import SettingsOrganization from "@/components/settings/SettingsOrganization";
import SettingsProfile from "@/components/settings/SettingsProfile";
import SettingsTeam from "@/components/settings/SettingsTeam";

// Components
import Layout from "@/components/Layout";
import LoadingSpinner from "@/components/ui/loading-spinner";

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

// Protected Route component
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

// Public Route component (redirect if authenticated)
const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

// Admin Route component
const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!user.is_superadmin) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <DndProvider backend={HTML5Backend}>
          <ToastProvider>
            <Router>
              <div className="App">
                <Toaster />
                <Routes>
                  {/* Public routes */}
                  <Route
                    path="/login"
                    element={
                      <PublicRoute>
                        <LoginPage />
                      </PublicRoute>
                    }
                  />
                  <Route
                    path="/register"
                    element={
                      <PublicRoute>
                        <RegisterPage />
                      </PublicRoute>
                    }
                  />

                  {/* Accept invitation (public, no auth) */}
                  <Route
                    path="/accept-invite/:token"
                    element={<AcceptInvitePage />}
                  />

                  {/* Protected routes */}
                  <Route
                    path="/dashboard"
                    element={
                      <ProtectedRoute>
                        <Layout>
                          <DashboardPage />
                        </Layout>
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/workflows"
                    element={
                      <ProtectedRoute>
                        <Layout>
                          <WorkflowsPage />
                        </Layout>
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/workflows/:id"
                    element={
                      <ProtectedRoute>
                        <Layout>
                          <WorkflowDetailPage />
                        </Layout>
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/workflows/:id/processing"
                    element={
                      <ProtectedRoute>
                        <ProcessingDashboard />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/settings"
                    element={
                      <ProtectedRoute>
                        <Layout>
                          <SettingsLayout />
                        </Layout>
                      </ProtectedRoute>
                    }
                  >
                    <Route index element={<SettingsProfile />} />
                    <Route
                      path="organization"
                      element={<SettingsOrganization />}
                    />
                    <Route path="team" element={<SettingsTeam />} />
                    <Route path="billing" element={<SettingsBilling />} />
                    <Route path="acorns" element={<SettingsAcorns />} />
                    <Route
                      path="integrations"
                      element={<SettingsIntegrations />}
                    />
                    <Route path="api-keys" element={<SettingsApiKeys />} />
                    <Route path="affiliate" element={<SettingsAffiliate />} />
                    <Route path="audit-log" element={<SettingsAuditLog />} />
                  </Route>
                  <Route
                    path="/emails"
                    element={
                      <ProtectedRoute>
                        <Layout>
                          <EmailQueuePage />
                        </Layout>
                      </ProtectedRoute>
                    }
                  />

                  <Route
                    path="/resources"
                    element={
                      <ProtectedRoute>
                        <Layout>
                          <ResourcesPage />
                        </Layout>
                      </ProtectedRoute>
                    }
                  />

                  {/* Contacts routes */}
                  <Route
                    path="/contacts"
                    element={<Navigate to="/contacts/persons" replace />}
                  />
                  <Route
                    path="/contacts/persons"
                    element={
                      <ProtectedRoute>
                        <Layout>
                          <ContactPersonsPage />
                        </Layout>
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/contacts/organizations"
                    element={
                      <ProtectedRoute>
                        <Layout>
                          <ContactOrganizationsPage />
                        </Layout>
                      </ProtectedRoute>
                    }
                  />

                  <Route
                    path="/admin"
                    element={
                      <AdminRoute>
                        <Layout>
                          <AdminPage />
                        </Layout>
                      </AdminRoute>
                    }
                  />

                  <Route
                    path="/admin/usage"
                    element={
                      <AdminRoute>
                        <Layout>
                          <AdminUsagePage />
                        </Layout>
                      </AdminRoute>
                    }
                  />

                  <Route
                    path="/admin/user/:id"
                    element={
                      <AdminRoute>
                        <Layout>
                          <AdminUserPage />
                        </Layout>
                      </AdminRoute>
                    }
                  />

                  <Route
                    path="/admin/org/:id"
                    element={
                      <AdminRoute>
                        <Layout>
                          <AdminOrgPage />
                        </Layout>
                      </AdminRoute>
                    }
                  />

                  <Route
                    path="/admin/models"
                    element={
                      <AdminRoute>
                        <Layout>
                          <AdminModelsPage />
                        </Layout>
                      </AdminRoute>
                    }
                  />

                  <Route
                    path="/admin/rag"
                    element={
                      <AdminRoute>
                        <Layout>
                          <AdminRAGPage />
                        </Layout>
                      </AdminRoute>
                    }
                  />

                  {/* Redirect root to dashboard */}
                  <Route
                    path="/"
                    element={<Navigate to="/dashboard" replace />}
                  />

                  {/* Catch all route */}
                  <Route
                    path="*"
                    element={
                      <div className="min-h-screen flex items-center justify-center">
                        <div className="text-center">
                          <h1 className="text-2xl font-bold text-gray-900">
                            404 - Page Not Found
                          </h1>
                          <p className="text-gray-600 mt-2">
                            The page you're looking for doesn't exist.
                          </p>
                        </div>
                      </div>
                    }
                  />
                </Routes>
              </div>
            </Router>
          </ToastProvider>
        </DndProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
