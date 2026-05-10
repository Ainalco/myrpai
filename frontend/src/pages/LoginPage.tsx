import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import LoadingSpinner from '@/components/ui/loading-spinner'
import { useAuth } from '@/contexts/AuthContext'

interface LoginForm {
  email: string
  password: string
}

const LoginPage: React.FC = () => {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>()

  const onSubmit = async (data: LoginForm) => {
    try {
      setIsLoading(true)
      setError(null)
      await login(data.email, data.password)

      // Check if there's a stored redirect path
      const redirectPath = sessionStorage.getItem('redirectAfterLogin')
      if (redirectPath) {
        sessionStorage.removeItem('redirectAfterLogin')
        navigate(redirectPath)
      } else {
        navigate('/dashboard')
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-scurry-foam py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-scurry-espresso">
            Workflow Platform
          </h1>
          <p className="mt-2 text-scurry-latte">
            Automate call transcript processing and CRM integration
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Sign in to your account</CardTitle>
            <CardDescription>
              Enter your credentials to access your workflows
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              {error && (
                <div className="bg-scurry-red-light border border-scurry-red/30 rounded-md p-3">
                  <p className="text-sm text-scurry-red">{error}</p>
                </div>
              )}

              <div>
                <label htmlFor="email" className="block text-sm font-medium text-scurry-espresso mb-1">
                  Email
                </label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@company.com"
                  {...register('email', { required: 'Email is required' })}
                  className={errors.email ? 'border-scurry-red' : ''}
                />
                {errors.email && (
                  <p className="mt-1 text-sm text-scurry-red">{errors.email.message}</p>
                )}
              </div>

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-scurry-espresso mb-1">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  {...register('password', { required: 'Password is required' })}
                  className={errors.password ? 'border-scurry-red' : ''}
                />
                {errors.password && (
                  <p className="mt-1 text-sm text-scurry-red">{errors.password.message}</p>
                )}
              </div>

              <Button
                type="submit"
                className="w-full"
                disabled={isLoading}
              >
                {isLoading ? (
                  <div className="flex items-center">
                    <LoadingSpinner size="sm" className="mr-2" />
                    Signing in...
                  </div>
                ) : (
                  'Sign in'
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-scurry-latte">
                Don't have an account?{' '}
                <Link
                  to="/register"
                  className="font-medium text-scurry-orange hover:text-scurry-orange-hover"
                >
                  Sign up
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default LoginPage
