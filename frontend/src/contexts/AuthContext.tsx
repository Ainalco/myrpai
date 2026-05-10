import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi, billingApi, User } from '@/lib/api'

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: {
    email: string
    password: string
    full_name?: string
    company_name?: string
    team_size?: string
    current_crm?: string
    meeting_tool?: string
    meetings_per_week?: string
    deal_cycle?: string
    challenge?: string
  }) => Promise<void>
  logout: () => void
  refreshAcorns: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: React.ReactNode
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [initialCheckDone, setInitialCheckDone] = useState(false)
  const queryClient = useQueryClient()

  // Check if user is logged in on mount
  const { data: userData, isLoading, isError } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: () => authApi.getMe().then((res) => res.data),
    enabled: !!localStorage.getItem('access_token'),
    retry: false,
  })

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.login({ email, password }),
    onSuccess: (response) => {
      const { access_token, refresh_token } = response.data
      localStorage.setItem('access_token', access_token)
      if (refresh_token) {
        localStorage.setItem('refresh_token', refresh_token)
      }
      // Refetch user data
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
    },
  })

  // Register mutation
  const registerMutation = useMutation({
    mutationFn: (data: {
      email: string
      password: string
      full_name?: string
      company_name?: string
      team_size?: string
      current_crm?: string
      meeting_tool?: string
      meetings_per_week?: string
      deal_cycle?: string
      challenge?: string
    }) => authApi.register(data),
    onSuccess: () => {
      // After successful registration, let the user login manually
    },
  })

  // Update user state when userData changes
  useEffect(() => {
    if (userData) {
      setUser(userData)
      setInitialCheckDone(true)
    } else if (isError || !localStorage.getItem('access_token')) {
      setUser(null)
      setInitialCheckDone(true)
    }
  }, [userData, isError])

  // Mark initial check as done when loading completes
  useEffect(() => {
    if (!isLoading && !initialCheckDone) {
      setInitialCheckDone(true)
    }
  }, [isLoading, initialCheckDone])

  const login = async (email: string, password: string) => {
    try {
      await loginMutation.mutateAsync({ email, password })
    } catch (error: any) {
      throw new Error(
        error.response?.data?.detail || 'Login failed. Please try again.'
      )
    }
  }

  const register = async (data: {
    email: string
    password: string
    full_name?: string
    company_name?: string
    team_size?: string
    current_crm?: string
    meeting_tool?: string
    meetings_per_week?: string
    deal_cycle?: string
    challenge?: string
  }) => {
    try {
      await registerMutation.mutateAsync(data)
    } catch (error: any) {
      throw new Error(
        error.response?.data?.detail || 'Registration failed. Please try again.'
      )
    }
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setUser(null)
    queryClient.clear()
    window.location.href = '/login'
  }

  const refreshAcorns = useCallback(async () => {
    try {
      const response = await billingApi.getAcornBalance()
      const { acorn_balance, acorn_allocation_mode, locked_acorn_allocation, locked_acorn_balance } = response.data
      setUser((prev) => {
        if (!prev) return null
        return {
          ...prev,
          locked_acorn_allocation: locked_acorn_allocation !== undefined ? locked_acorn_allocation : prev.locked_acorn_allocation,
          locked_acorn_balance: locked_acorn_balance !== undefined ? locked_acorn_balance : prev.locked_acorn_balance,
          account: prev.account
            ? { ...prev.account, acorn_balance, acorn_allocation_mode: acorn_allocation_mode ?? prev.account.acorn_allocation_mode }
            : prev.account,
        }
      })
    } catch {
      // Silently fail - acorn balance refresh is non-critical
    }
  }, [])

  const value: AuthContextType = {
    user,
    loading: isLoading || (!initialCheckDone && !!localStorage.getItem('access_token')),
    login,
    register,
    logout,
    refreshAcorns,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
