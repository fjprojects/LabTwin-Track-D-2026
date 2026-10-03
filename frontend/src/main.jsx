import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import ClassroomPortal from './ClassroomPortal.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ClassroomPortal />
  </StrictMode>,
)
