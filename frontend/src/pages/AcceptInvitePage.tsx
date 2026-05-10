import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { teamApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Loader2, CheckCircle } from 'lucide-react'

export default function AcceptInvitePage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [success, setSuccess] = useState(false)

  const { data: invite, isLoading, error } = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => teamApi.getInviteInfo(token!).then(r => r.data),
    enabled: !!token,
  })

  const acceptMutation = useMutation({
    mutationFn: () => teamApi.acceptInvite(token!, { token: token!, password, full_name: fullName }),
    onSuccess: () => {
      setSuccess(true)
      setTimeout(() => navigate('/login'), 3000)
    },
  })

  if (isLoading) return <div className="flex justify-center items-center h-screen"><Loader2 className="h-8 w-8 animate-spin" /></div>
  if (error) return (
    <div className="flex justify-center items-center h-screen">
      <Card className="w-full max-w-md">
        <CardContent className="pt-6 text-center text-red-600">
          This invitation is invalid or has expired.
        </CardContent>
      </Card>
    </div>
  )

  if (success) return (
    <div className="flex justify-center items-center h-screen">
      <Card className="w-full max-w-md">
        <CardContent className="pt-6 text-center space-y-3">
          <CheckCircle className="h-12 w-12 text-green-500 mx-auto" />
          <h2 className="text-xl font-bold">Welcome to the team!</h2>
          <p className="text-muted-foreground">Redirecting to login...</p>
        </CardContent>
      </Card>
    </div>
  )

  return (
    <div className="flex justify-center items-center min-h-screen bg-gray-50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle>Join {invite?.org_name}</CardTitle>
          <CardDescription>You've been invited as {invite?.role}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">Email</label>
            <Input value={invite?.email || ''} disabled className="bg-gray-50" />
          </div>
          <div>
            <label className="text-sm font-medium">Full Name</label>
            <Input value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Your name" />
          </div>
          <div>
            <label className="text-sm font-medium">Password</label>
            <Input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Create a password" />
          </div>
          <Button
            className="w-full"
            onClick={() => acceptMutation.mutate()}
            disabled={!password || acceptMutation.isPending}
          >
            {acceptMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Join Team
          </Button>
          {acceptMutation.error && (
            <p className="text-sm text-red-600 text-center">
              {(acceptMutation.error as any).response?.data?.detail || 'Failed to accept invitation'}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
