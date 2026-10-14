// Lightweight, dependency-free navigation icons with a shared accessible size.
const strokes = {
  Dashboard: ["M3 3h7v7H3z","M14 3h7v7h-7z","M3 14h7v7H3z","M14 14h7v7h-7z"],
  "Ask LabTwin": ["M21 11.5a8.4 8.4 0 0 1-8.5 8.5 9 9 0 0 1-4-.9L3 21l1.9-5.5a9 9 0 1 1 16.1-4z","M8 10h8","M8 14h5"],
  "My Courses": ["M4 19.5A2.5 2.5 0 0 1 6.5 17H21","M6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"],
  "Course Materials": ["M4 19.5A2.5 2.5 0 0 1 6.5 17H21","M6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"],
  "Learning Path": ["M4 18h4l3-6 3 3 6-9","M17 6h3v3"],
  Practice: ["M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8l-5-5H8z","M13 3v6h6","M7 14l2 2 4-4"],
  Assessments: ["M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8l-5-5H8z","M13 3v6h6","M7 14l2 2 4-4"],
  Assignments: ["M8 4h-3a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-3","M9 3h6v4H9z","M8 12h8","M8 16h6"],
  Viva: ["M12 3a4 4 0 0 0-4 4v5a4 4 0 0 0 8 0V7a4 4 0 0 0-4-4z","M5 11v1a7 7 0 0 0 14 0v-1","M12 19v3","M8 22h8"],
  "Mastery Map": ["M3 3h7v7H3z","M14 3h7v7h-7z","M3 14h7v7H3z","M14 14h7v7h-7z","M10 6h4","M6 10v4","M17 10v4","M10 17h4"],
  Progress: ["M3 3v18h18","M7 16l4-5 3 2 6-7"],
  Classes: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2","M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z","M22 21v-2a4 4 0 0 0-3-3.87","M16 3.13a4 4 0 0 1 0 7.75"],
  Students: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2","M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z","M22 21v-2a4 4 0 0 0-3-3.87","M16 3.13a4 4 0 0 1 0 7.75"],
  "AI Insights": ["M4 19v-5","M9 19V9","M14 19v-8","M19 19V5","M2 21h20"],
  Evaluation: ["M4 19v-5","M9 19V9","M14 19v-8","M19 19V5","M2 21h20"],
  Reports: ["M6 2h9l5 5v15H6z","M14 2v6h6","M9 12h7","M9 16h7"],
  "Demo Mode": ["M12 2l2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5z"],
};
export default function NavIcon({ name }) {
  return <svg className="navIcon" aria-hidden="true" focusable="false" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {(strokes[name] || strokes.Dashboard).map((d, i) => <path d={d} key={i} />)}
  </svg>;
}
