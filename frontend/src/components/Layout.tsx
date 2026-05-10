import {
  Building2,
  ChevronRight,
  LayoutDashboard,
  LogOut,
  Mail,
  Menu,
  Package,
  Settings,
  Shield,
  User,
  Users,
  Workflow,
  X,
} from "lucide-react";
import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { AcornBalance } from "@/components/ui/acorn-balance";
import { Button } from "@/components/ui/button";
import { TrialBanner } from "@/components/ui/trial-banner";
import { useAuth } from "@/contexts/AuthContext";
import { useState } from "react";

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [contactsOpen, setContactsOpen] = useState(
    location.pathname.startsWith("/contacts"),
  );

  // Top nav items (before Contacts)
  const topNav = [
    {
      name: "Dashboard",
      href: "/dashboard",
      icon: LayoutDashboard,
      current: location.pathname === "/dashboard",
    },
    {
      name: "Workflows",
      href: "/workflows",
      icon: Workflow,
      current: location.pathname.startsWith("/workflows"),
    },
    {
      name: "Email Queue",
      href: "/emails",
      icon: Mail,
      current: location.pathname === "/emails",
    },
    {
      name: "Resources",
      href: "/resources",
      icon: Package,
      current: location.pathname === "/resources",
    },
  ];

  // Contacts sub-nav
  const isContactsActive = location.pathname.startsWith("/contacts");
  const contactsSubNav = [
    {
      name: "Persons",
      href: "/contacts/persons",
      icon: User,
      current: location.pathname === "/contacts/persons",
    },
    {
      name: "Organizations",
      href: "/contacts/organizations",
      icon: Building2,
      current: location.pathname === "/contacts/organizations",
    },
  ];

  // Bottom nav items (after Contacts)
  const bottomNav = [
    {
      name: "Settings",
      href: "/settings",
      icon: Settings,
      current: location.pathname.startsWith("/settings"),
    },
    ...(user?.is_superadmin
      ? [
          {
            name: "Admin",
            href: "/admin",
            icon: Shield,
            current: location.pathname === "/admin",
          },
        ]
      : []),
  ];

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  // Shared nav item renderer
  const renderNavItem = (
    item: { name: string; href: string; icon: any; current: boolean },
    onClick?: () => void,
  ) => {
    const Icon = item.icon;
    return (
      <Link
        key={item.name}
        to={item.href}
        className={`group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold ${
          item.current
            ? "bg-scurry-orange-light text-scurry-orange"
            : "text-scurry-latte hover:text-scurry-orange hover:bg-scurry-foam"
        }`}
        onClick={onClick}
      >
        <Icon
          className={`h-5 w-5 shrink-0 ${
            item.current
              ? "text-scurry-orange"
              : "text-scurry-gray-muted group-hover:text-scurry-orange"
          }`}
        />
        {item.name}
      </Link>
    );
  };

  // Shared mobile nav item renderer
  const renderMobileNavItem = (item: {
    name: string;
    href: string;
    icon: any;
    current: boolean;
  }) => {
    const Icon = item.icon;
    return (
      <Link
        key={item.name}
        to={item.href}
        className={`group flex items-center px-2 py-2 text-sm font-medium rounded-md mb-1 ${
          item.current
            ? "bg-scurry-orange-light text-scurry-espresso"
            : "text-scurry-latte hover:bg-scurry-foam hover:text-scurry-espresso"
        }`}
        onClick={() => setSidebarOpen(false)}
      >
        <Icon
          className={`mr-3 h-5 w-5 ${
            item.current
              ? "text-scurry-orange"
              : "text-scurry-gray-muted group-hover:text-scurry-latte"
          }`}
        />
        {item.name}
      </Link>
    );
  };

  return (
    <div className="min-h-screen bg-scurry-gray-light">
      <TrialBanner />
      {/* Mobile sidebar */}
      <div
        className={`fixed inset-0 z-50 lg:hidden ${sidebarOpen ? "block" : "hidden"}`}
      >
        <div
          className="fixed inset-0 bg-scurry-espresso bg-opacity-75"
          onClick={() => setSidebarOpen(false)}
        />
        <div className="fixed inset-y-0 left-0 w-64 bg-white shadow-xl">
          <div className="flex h-16 items-center justify-between px-4">
            <Link to="/dashboard" className="flex items-center">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-scurry-orange">
                <Workflow className="h-5 w-5 text-white" />
              </div>
              <span className="ml-2 text-lg font-semibold text-scurry-espresso">
                Workflow Platform
              </span>
            </Link>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(false)}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
          <nav className="mt-5 px-2">
            {/* Top nav */}
            {topNav.map((item) => renderMobileNavItem(item))}

            {/* Contacts — expandable */}
            <button
              onClick={() => setContactsOpen(!contactsOpen)}
              className={`group flex items-center w-full px-2 py-2 text-sm font-medium rounded-md mb-1 ${
                isContactsActive
                  ? "bg-scurry-orange-light text-scurry-espresso"
                  : "text-scurry-latte hover:bg-scurry-foam hover:text-scurry-espresso"
              }`}
            >
              <Users
                className={`mr-3 h-5 w-5 ${
                  isContactsActive
                    ? "text-scurry-orange"
                    : "text-scurry-gray-muted group-hover:text-scurry-latte"
                }`}
              />
              <span className="flex-1 text-left">Contacts</span>
              <ChevronRight
                className={`h-4 w-4 text-scurry-gray-muted transition-transform ${contactsOpen ? "rotate-90" : ""}`}
              />
            </button>
            {contactsOpen && (
              <div className="ml-6 pl-3 border-l-2 border-scurry-gray-border mb-1">
                {contactsSubNav.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.name}
                      to={item.href}
                      className={`group flex items-center px-2 py-1.5 text-sm font-medium rounded-md mb-0.5 ${
                        item.current
                          ? "bg-scurry-orange-light text-scurry-orange"
                          : "text-scurry-latte hover:bg-scurry-foam hover:text-scurry-espresso"
                      }`}
                      onClick={() => setSidebarOpen(false)}
                    >
                      <Icon
                        className={`mr-2 h-4 w-4 ${
                          item.current
                            ? "text-scurry-orange"
                            : "text-scurry-gray-muted"
                        }`}
                      />
                      {item.name}
                    </Link>
                  );
                })}
              </div>
            )}

            {/* Bottom nav */}
            {bottomNav.map((item) => renderMobileNavItem(item))}
          </nav>
        </div>
      </div>

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-64 lg:flex-col">
        <div className="flex grow flex-col gap-y-5 overflow-y-auto border-r border-scurry-gray-border bg-white px-6">
          <div className="flex h-16 shrink-0 items-center">
            <Link to="/dashboard" className="flex items-center">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-scurry-orange">
                <Workflow className="h-5 w-5 text-white" />
              </div>
              <span className="ml-2 text-lg font-semibold text-scurry-espresso">
                Workflow Platform
              </span>
            </Link>
          </div>
          <nav className="flex flex-1 flex-col">
            <ul role="list" className="flex flex-1 flex-col gap-y-7">
              <li>
                <ul role="list" className="-mx-2 space-y-1">
                  {/* Top nav items */}
                  {topNav.map((item) => (
                    <li key={item.name}>{renderNavItem(item)}</li>
                  ))}

                  {/* Contacts — expandable */}
                  <li>
                    <button
                      onClick={() => setContactsOpen(!contactsOpen)}
                      className={`group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold w-full ${
                        isContactsActive
                          ? "bg-scurry-orange-light text-scurry-orange"
                          : "text-scurry-latte hover:text-scurry-orange hover:bg-scurry-foam"
                      }`}
                    >
                      <Users
                        className={`h-5 w-5 shrink-0 ${
                          isContactsActive
                            ? "text-scurry-orange"
                            : "text-scurry-gray-muted group-hover:text-scurry-orange"
                        }`}
                      />
                      <span className="flex-1 text-left">Contacts</span>
                      <ChevronRight
                        className={`h-4 w-4 text-scurry-gray-muted transition-transform ${contactsOpen ? "rotate-90" : ""}`}
                      />
                    </button>

                    {contactsOpen && (
                      <ul
                        role="list"
                        className="ml-6 pl-3 mt-1 space-y-0.5 border-l-2 border-scurry-gray-border"
                      >
                        {contactsSubNav.map((sub) => {
                          const SubIcon = sub.icon;
                          return (
                            <li key={sub.name}>
                              <Link
                                to={sub.href}
                                className={`group flex gap-x-2 rounded-md px-2 py-1.5 text-sm font-medium ${
                                  sub.current
                                    ? "bg-scurry-orange-light text-scurry-orange"
                                    : "text-scurry-latte hover:text-scurry-orange hover:bg-scurry-foam"
                                }`}
                              >
                                <SubIcon
                                  className={`h-4 w-4 shrink-0 ${
                                    sub.current
                                      ? "text-scurry-orange"
                                      : "text-scurry-gray-muted group-hover:text-scurry-orange"
                                  }`}
                                />
                                {sub.name}
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </li>

                  {/* Bottom nav items */}
                  {bottomNav.map((item) => (
                    <li key={item.name}>{renderNavItem(item)}</li>
                  ))}
                </ul>
              </li>
              <li className="mt-auto">
                <div className="px-2 py-2">
                  <AcornBalance />
                </div>
                <div className="flex items-center gap-x-4 px-2 py-3 text-sm font-semibold leading-6 text-scurry-espresso">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-scurry-gray-border">
                    <User className="h-4 w-4 text-scurry-latte" />
                  </div>
                  <span className="sr-only">Your profile</span>
                  <div className="flex-1">
                    <div className="text-sm font-medium text-scurry-espresso">
                      {user?.full_name || user?.email}
                    </div>
                    <div className="text-xs text-scurry-gray-muted">
                      {user?.email}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleLogout}
                    className="h-8 w-8"
                  >
                    <LogOut className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            </ul>
          </nav>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Top bar for mobile */}
        <div className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-x-4 border-b border-scurry-gray-border bg-white px-4 shadow-sm sm:gap-x-6 sm:px-6 lg:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>
          <div className="flex flex-1 justify-end">
            <div className="flex items-center gap-x-4">
              <AcornBalance />
              <div className="text-sm font-medium text-scurry-espresso">
                {user?.full_name || user?.email}
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleLogout}
                className="h-8 w-8"
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Page content */}
        <main className="py-3 sm:py-4 overflow-x-hidden">
          <div className="px-2 sm:px-4 lg:px-6">{children}</div>
        </main>
      </div>
    </div>
  );
};

export default Layout;
