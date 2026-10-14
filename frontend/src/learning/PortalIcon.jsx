// Inline SVGs keep navigation icons available without icon fonts or a CDN.
const paths = {
  Dashboard: ["M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z"],
  "Ask LabTwin": ["M4 3h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H9l-5 4V4a1 1 0 0 1 1-1z", "M8 7h9 M8 11h6"],
  "My Courses": ["M12 5C9 3 5 3 2 4v15c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1z M12 5v15"],
  "Course Materials": ["M3 6h7l2 2h9v12H3z", "M3 6V4h7l2 2h7v2 M7 12h10 M7 16h7"],
  Classes: ["M3 21h18 M5 21V9l7-6 7 6v12 M9 21v-6h6v6 M8 10h1 M15 10h1"],
  "Learning Path": ["M6 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M18 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4z", "M6 7v3c0 2 2 3 4 3h4c2 0 4 1 4 3v1"],
  Practice: ["M8 6 2 12l6 6 M16 6l6 6-6 6 M14 3l-4 18"],
  "Programming Lab": ["M3 4h18v16H3z", "m6 9 3 3-3 3 M12 15h5"],
  Assessments: ["M9 3h6v4H9z M9 5H5v16h14V5h-4", "m8 12 1 1 2-2 M13 12h3 m-8 5 1 1 2-2 M13 17h3"],
  Assignments: ["M8 3h8v4H8z M8 5H4v16h16V5h-4 M8 11h8 M8 15h8 M8 18h5"],
  Students: ["M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M2 21v-2a7 7 0 0 1 14 0v2", "M17 4a4 4 0 0 1 0 7 M19 14a6 6 0 0 1 3 5v2"],
  Viva: ["M12 15a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v7a3 3 0 0 0 3 3z", "M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3 M8 22h8"],
  "Mastery Map": ["M4 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M20 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M12 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M6 6h12 M5 8l5 7 M19 8l-5 7"],
  Progress: ["M3 3v18h18 M7 15l4-5 4 3 6-8 M17 5h4v4"],
  "AI Insights": ["M9 18h6 M10 21h4 M8 15a6 6 0 1 1 8 0c-1 1-1 2-1 3H9c0-1 0-2-1-3z", "M12 1v1 M2 9h2 M20 9h2 M4 3l2 2 M18 5l2-2"],
  Evaluation: ["M4 18a9 9 0 1 1 16 0H4z M12 14l5-6 M7 10h1 M11 6v1 M18 13h1"],
  Reports: ["M4 2h10l6 6v14H4z M14 2v6h6", "M8 18v-4 M12 18v-7 M16 18v-3"],
  "Demo Mode": ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M10 7l7 5-7 5z"],
  "Recovery phone": ["M8 3H4v4c0 7 6 13 13 13h4v-4l-5-2-2 3a13 13 0 0 1-7-7l3-2-2-5z"],
  "Sign out": ["M10 3H3v18h7 M8 12h13 m-4-4 4 4-4 4"],
  Refresh: ["M20 7a9 9 0 0 0-15-2L2 8 M2 3v5h5 M4 17a9 9 0 0 0 15 2l3-3 M22 21v-5h-5"],
};

export default function PortalIcon({ name, className = "" }) {
  return <svg className={`portalIcon ${className}`} data-icon={name} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {(paths[name] || paths.Dashboard).map((d, index) => <path key={index} d={d} />)}
  </svg>;
}
