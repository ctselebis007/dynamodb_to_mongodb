import { Navigate, createBrowserRouter, type RouteObject } from 'react-router'
import { Layout, ReadyGate } from './core/Layout'
import { loadModules } from './core/modules'
import { SetupPage } from './core/setup/SetupPage'

const modules = loadModules()

const routes: RouteObject[] = [
  {
    path: '/',
    element: <Layout modules={modules} />,
    children: [
      { index: true, element: <Navigate to="/setup" replace /> },
      { path: 'setup', element: <SetupPage /> },
      ...modules.map((m) => ({
        path: m.route.path,
        element: m.route.public ? m.route.element : <ReadyGate>{m.route.element}</ReadyGate>,
      })),
      { path: '*', element: <Navigate to="/setup" replace /> },
    ],
  },
]

export const router = createBrowserRouter(routes)
