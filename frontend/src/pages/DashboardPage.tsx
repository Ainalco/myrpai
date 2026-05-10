import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  BarChart3,
  Workflow,
  Clock,
  CheckCircle,
  XCircle,
  Plus,
  TrendingUp,
  Activity
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import LoadingSpinner from '@/components/ui/loading-spinner'
import { workflowApi } from '@/lib/api'
import { formatExecutionTime } from '@/lib/utils'
const DashboardPage: React.FC = () => {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['workflow-stats'],
    queryFn: () => workflowApi.getStats().then(res => res.data),
  })
  const { data: recentWorkflows, isLoading: workflowsLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: () => workflowApi.getAll().then(res => res.data.slice(0, 5)), // Get first 5
  })
  if (statsLoading || workflowsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    )
  }
  const successRate = stats ?
    stats.total_executions > 0
      ? Math.round((stats.successful_executions / stats.total_executions) * 100)
      : 0
    : 0
  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header with Light Gradient */}
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light -mx-8 -mt-8 px-4 sm:px-6 lg:px-8 py-6 sm:py-8 rounded-b-2xl shadow-md border-b-2 border-scurry-orange/20 relative overflow-hidden">
        {/* Decorative accent */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-scurry-orange/10 to-transparent rounded-bl-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-scurry-energy-burst/10 to-transparent rounded-tr-full" />

        <div className="flex items-center justify-between relative z-10">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-scurry-espresso font-display">
              Dashboard
            </h1>
            <p className="text-sm sm:text-base text-scurry-latte mt-2">
              Monitor your workflow automation platform
            </p>
          </div>
          <Link to="/workflows">
            <Button className="bg-gradient-to-r from-scurry-orange to-scurry-orange-hover text-white hover:from-scurry-orange-hover hover:to-scurry-orange shadow-md hover:shadow-lg hover:scale-105 transition-all duration-200">
              <Plus className="h-4 w-4 mr-2" />
              Create Workflow
            </Button>
          </Link>
        </div>
      </div>
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
        <Card className="overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow">
          <div className="h-1.5 bg-gradient-to-r from-scurry-orange to-scurry-energy-burst" />
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4">
            <CardTitle className="text-sm font-medium text-scurry-latte">Total Workflows</CardTitle>
            <div className="p-2 rounded-full bg-scurry-orange-light">
              <Workflow className="h-4 w-4 text-scurry-orange" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-scurry-espresso">{stats?.total_workflows || 0}</div>
            <p className="text-xs text-scurry-latte mt-1">
              <span className="text-scurry-green font-medium">{stats?.active_workflows || 0}</span> active
            </p>
          </CardContent>
        </Card>
        <Card className="overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow">
          <div className="h-1.5 bg-gradient-to-r from-scurry-blue-text to-scurry-latte" />
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4">
            <CardTitle className="text-sm font-medium text-scurry-latte">Total Executions</CardTitle>
            <div className="p-2 rounded-full bg-scurry-blue-bg">
              <Activity className="h-4 w-4 text-scurry-blue-text" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-scurry-espresso">{stats?.total_executions || 0}</div>
            <p className="text-xs text-scurry-latte mt-1">
              All time executions
            </p>
          </CardContent>
        </Card>
        <Card className="overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow">
          <div className="h-1.5 bg-gradient-to-r from-scurry-green to-scurry-energy-burst" />
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4">
            <CardTitle className="text-sm font-medium text-scurry-latte">Success Rate</CardTitle>
            <div className="p-2 rounded-full bg-scurry-green-light">
              <TrendingUp className="h-4 w-4 text-scurry-green" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-scurry-espresso">{successRate}%</div>
            <p className="text-xs text-scurry-latte mt-1">
              <span className="text-scurry-green font-medium">{stats?.successful_executions || 0}</span> successful
            </p>
          </CardContent>
        </Card>
        <Card className="overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow">
          <div className="h-1.5 bg-gradient-to-r from-scurry-energy-burst to-scurry-orange" />
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4">
            <CardTitle className="text-sm font-medium text-scurry-latte">Avg Execution Time</CardTitle>
            <div className="p-2 rounded-full bg-scurry-orange-light">
              <Clock className="h-4 w-4 text-scurry-energy-burst" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-scurry-espresso">
              {stats?.avg_execution_time
                ? formatExecutionTime(Math.round(stats.avg_execution_time))
                : 'N/A'
              }
            </div>
            <p className="text-xs text-scurry-latte mt-1">
              Average duration
            </p>
          </CardContent>
        </Card>
      </div>
      {/* Quick Stats and Recent Workflows */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5">
        {/* Execution Status Breakdown */}
        <Card className="border-0 shadow-md">
          <CardHeader className="border-b border-scurry-gray-border/50 bg-gradient-to-r from-scurry-foam to-white">
            <CardTitle className="text-scurry-espresso">Execution Status</CardTitle>
            <CardDescription className="text-scurry-latte">
              Breakdown of workflow execution results
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-5">
            <div className="flex items-center justify-between p-3 rounded-lg bg-scurry-green-light/50 hover:bg-scurry-green-light transition-colors">
              <div className="flex items-center">
                <div className="p-1.5 rounded-full bg-scurry-green-light mr-3">
                  <CheckCircle className="h-4 w-4 text-scurry-green" />
                </div>
                <span className="text-sm font-medium text-scurry-espresso">Successful</span>
              </div>
              <div className="text-lg font-bold text-scurry-green">
                {stats?.successful_executions || 0}
              </div>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-scurry-red-light/50 hover:bg-scurry-red-light transition-colors">
              <div className="flex items-center">
                <div className="p-1.5 rounded-full bg-scurry-red-light mr-3">
                  <XCircle className="h-4 w-4 text-scurry-red" />
                </div>
                <span className="text-sm font-medium text-scurry-espresso">Failed</span>
              </div>
              <div className="text-lg font-bold text-scurry-red">
                {stats?.failed_executions || 0}
              </div>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-scurry-orange-light/50 hover:bg-scurry-orange-light transition-colors">
              <div className="flex items-center">
                <div className="p-1.5 rounded-full bg-scurry-orange-light mr-3">
                  <BarChart3 className="h-4 w-4 text-scurry-orange" />
                </div>
                <span className="text-sm font-medium text-scurry-espresso">Total</span>
              </div>
              <div className="text-lg font-bold text-scurry-orange">
                {stats?.total_executions || 0}
              </div>
            </div>
          </CardContent>
        </Card>
        {/* Recent Workflows */}
        <Card className="border-0 shadow-md">
          <CardHeader className="border-b border-scurry-gray-border/50 bg-gradient-to-r from-scurry-foam to-white">
            <CardTitle className="text-scurry-espresso">Recent Workflows</CardTitle>
            <CardDescription className="text-scurry-latte">
              Your most recently updated workflows
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-5">
            {recentWorkflows && recentWorkflows.length > 0 ? (
              <div className="space-y-3">
                {recentWorkflows.map((workflow) => (
                  <div key={workflow.id} className="flex items-center justify-between p-3 border border-scurry-gray-border rounded-lg hover:border-scurry-orange hover:bg-scurry-orange-light/30 hover:shadow-sm transition-all group">
                    <div className="flex-1">
                      <Link
                        to={`/workflows/${workflow.id}`}
                        className="font-medium text-scurry-espresso group-hover:text-scurry-orange transition-colors"
                      >
                        {workflow.name}
                      </Link>
                      {workflow.description && (
                        <p className="text-sm text-scurry-latte mt-1 line-clamp-1">
                          {workflow.description}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center space-x-3 ml-4">
                      <div className={`w-2.5 h-2.5 rounded-full ring-2 ring-offset-1 ${
                        workflow.is_active ? 'bg-scurry-green ring-scurry-green/30' : 'bg-scurry-gray-muted ring-scurry-gray-muted/30'
                      }`} />
                      <span className="text-xs text-scurry-latte bg-scurry-gray-light px-2 py-1 rounded-full">
                        {workflow.components.length} components
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <div className="p-4 rounded-full bg-scurry-orange-light inline-block mb-4">
                  <Workflow className="h-10 w-10 text-scurry-orange" />
                </div>
                <h3 className="text-sm font-medium text-scurry-espresso mb-2">
                  No workflows yet
                </h3>
                <p className="text-sm text-scurry-latte mb-4">
                  Get started by creating your first workflow
                </p>
                <Link to="/workflows">
                  <Button size="sm" className="bg-scurry-orange hover:bg-scurry-orange-hover shadow-md">
                    <Plus className="h-4 w-4 mr-2" />
                    Create Workflow
                  </Button>
                </Link>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      {/* Quick Actions */}
      <Card className="border-0 shadow-md overflow-hidden">
        <CardHeader className="border-b border-scurry-gray-border/50 bg-gradient-to-r from-scurry-foam to-white">
          <CardTitle className="text-scurry-espresso">Quick Actions</CardTitle>
          <CardDescription className="text-scurry-latte">
            Common tasks to get you started
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Link to="/workflows" className="block group">
              <div className="p-5 border-2 border-scurry-orange/20 rounded-xl hover:border-scurry-orange bg-gradient-to-br from-white to-scurry-orange-light/30 hover:to-scurry-orange-light hover:shadow-md transition-all">
                <div className="p-3 rounded-full bg-scurry-orange-light inline-block mb-3 group-hover:scale-110 transition-transform">
                  <Plus className="h-6 w-6 text-scurry-orange" />
                </div>
                <h3 className="font-semibold text-scurry-espresso mb-1 group-hover:text-scurry-orange transition-colors">Create Workflow</h3>
                <p className="text-sm text-scurry-latte">
                  Set up a new automation workflow
                </p>
              </div>
            </Link>
            <Link to="/workflows" className="block group">
              <div className="p-5 border-2 border-scurry-green/20 rounded-xl hover:border-scurry-green bg-gradient-to-br from-white to-scurry-green-light/30 hover:to-scurry-green-light hover:shadow-md transition-all">
                <div className="p-3 rounded-full bg-scurry-green-light inline-block mb-3 group-hover:scale-110 transition-transform">
                  <Workflow className="h-6 w-6 text-scurry-green" />
                </div>
                <h3 className="font-semibold text-scurry-espresso mb-1 group-hover:text-scurry-green transition-colors">Manage Workflows</h3>
                <p className="text-sm text-scurry-latte">
                  View and edit existing workflows
                </p>
              </div>
            </Link>
            <div className="p-5 border-2 border-scurry-gray-border/50 rounded-xl bg-gradient-to-br from-white to-scurry-gray-light/50 opacity-60 cursor-not-allowed">
              <div className="p-3 rounded-full bg-scurry-gray-light inline-block mb-3">
                <BarChart3 className="h-6 w-6 text-scurry-gray-muted" />
              </div>
              <h3 className="font-semibold text-scurry-espresso mb-1">Analytics</h3>
              <p className="text-sm text-scurry-latte">
                Coming soon - detailed analytics
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
export default DashboardPage
