import { useEffect, useRef, useState } from "react";
import api from "../api";
import { API } from "../api";
import { get, errorText } from "./api";
import AskLabTwin from "./AskLabTwin";
import CourseMaterials, { CourseSetup } from "./CourseMaterials";
import PracticeWorkspace from "./PracticeWorkspace";
import VivaWorkspace from "./VivaWorkspace";
import { LearningPath, MasteryMap, ProgressReport, StudentDashboard } from "./LearningViews";
import TeacherInsights from "./TeacherInsights";
import AssessmentManager from "./AssessmentManager";
import DemoPanel from "./DemoPanel";
import SourceViewer from "./SourceViewer";
import AssessmentWorkspace from "./AssessmentWorkspace";
import EvaluationDashboard from "./EvaluationDashboard";
import "./LearningPortal.css";

const studentNav = ["Dashboard", "Ask LabTwin", "My Courses", "Learning Path", "Practice", "Assessments", "Assignments", "Viva", "Mastery Map", "Progress"];
const teacherNav = ["Dashboard", "Classes", "Course Materials", "Assignments", "Students", "Assessments", "AI Insights", "Evaluation", "Reports"];

export default function LearningPortal({ account, onSignOut, onSwitchAccount, renderClassrooms, renderLab }) {
  const teacher = account.role === "teacher";
  const [page, setPage] = useState("Dashboard"), [courses, setCourses] = useState([]), [courseId, setCourseId] = useState(null), [revision, setRevision] = useState(0), [error, setError] = useState("");
  const [sourceId, setSourceId] = useState(null), [lecture, setLecture] = useState(null), [practiceTopic, setPracticeTopic] = useState(null), [practiceMode, setPracticeMode] = useState("adaptive"), [vivaTarget, setVivaTarget] = useState(null), [sharing, setSharing] = useState(false);
  const teacherSession = useRef(null);
  const course = courses.find(item => item.id === Number(courseId)) || courses[0] || null;
  async function refresh() {
    try { const data = await get("courses/"); setCourses(data.courses); setError(""); }
    catch (err) { setError(errorText(err)); }
  }
  useEffect(() => { refresh(); setPage(previous => previous === "Demo Mode" ? previous : "Dashboard"); }, [account.id]);
  useEffect(() => {
    setLecture(previous => previous?.course_id === course?.id ? previous : null);
    setVivaTarget(previous => course?.topics.some(topic => topic.id === previous?.topic_id) ? previous : null);
    setPracticeTopic(previous => course?.topics.some(topic => topic.id === previous) ? previous : null);
  }, [course]);
  useEffect(() => {
    const openHash = () => { const match = location.hash.match(/^#source=(\d+)$/); if (match) setSourceId(Number(match[1])); };
    const capture = event => setSharing(event.detail.active);
    openHash(); window.addEventListener("hashchange", openHash); window.addEventListener("labtwin-sharing", capture);
    return () => { window.removeEventListener("hashchange", openHash); window.removeEventListener("labtwin-sharing", capture); };
  }, []);
  const changed = () => { setRevision(v => v + 1); refresh(); };
  const onSource = id => { setSourceId(id); history.replaceState(null, "", `#source=${id}`); };
  const onPractice = id => { setPracticeTopic(id); setPracticeMode("adaptive"); setPage("Practice"); };
  const onViva = target => { if (target.course_id) setCourseId(target.course_id); setVivaTarget(target); setPage("Viva"); };
  async function preview(data) {
    teacherSession.current = { token: sessionStorage.getItem("labtwin_access_token"), account };
    sessionStorage.setItem("labtwin_access_token", data.token); await onSwitchAccount(data.account); setPage("Demo Mode");
  }
  async function returnTeacher() {
    const previous = teacherSession.current;
    if (!previous) return;
    try { await api.post(`${API}/auth/logout/`, {}); } catch { /* The short demo token expires independently. */ }
    sessionStorage.setItem("labtwin_access_token", previous.token); await onSwitchAccount(previous.account); teacherSession.current = null; setPage("Demo Mode"); changed();
  }
  const classVisible = teacher ? ["Classes", "Assignments", "Students", "Reports"].includes(page) : ["My Courses", "Assignments"].includes(page);
  const noCoursePages = ["Ask LabTwin", "Learning Path", "Mastery Map", "Progress", "Course Materials", "Assessments", "AI Insights", "Viva"];
  return <div className="learningShell classroomPortal">
    <aside className="learningSidebar"><a href="#" className="labtwinBrand" onClick={e => { e.preventDefault(); setPage("Dashboard"); }}>Lab<span>Twin</span><small>Learn with understanding</small></a><p className="roleLabel">{teacher ? "TEACHER WORKSPACE" : "STUDENT WORKSPACE"}</p><nav aria-label={`${teacher ? "Teacher" : "Student"} navigation`}>{(teacher ? teacherNav : studentNav).map(item => <button key={item} aria-current={page === item ? "page" : undefined} onClick={() => setPage(item)}><span className="navDot" />{item}</button>)}<button className="demoNav" aria-current={page === "Demo Mode" ? "page" : undefined} onClick={() => setPage("Demo Mode")}><span aria-hidden="true">✦</span> Demo Mode</button></nav><div className="sidebarFooter"><strong>{account.name}</strong><span>{account.role}</span><button className="secondary" onClick={onSignOut}>Sign out</button></div></aside>
    <main className="learningMain"><header className="learningTopbar"><div><p className="eyebrow">{teacher ? "TEACHER" : "STUDENT"} · LABTWIN</p><h1>{page}</h1></div><div className="courseSelect"><label>Current course<select aria-label="Current course" value={course?.id || ""} onChange={e => setCourseId(Number(e.target.value))}><option value="" disabled>{courses.length ? "Select course" : "No courses yet"}</option>{courses.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button className="secondary" onClick={changed}>Refresh</button></div></header>
      {sharing && <div className="captureBanner" role="status">Screen or camera sharing is active in your classroom assignment. <button onClick={() => window.dispatchEvent(new Event("labtwin-stop-sharing"))}>Stop all sharing</button></div>}
      {teacherSession.current && <div className="demoPreviewBanner">Isolated demo learner · <button className="secondary" onClick={returnTeacher}>Return to teacher</button></div>}
      {error && <p role="alert">{error}</p>}
      {!course && page === "Dashboard" && <section className="learningHero"><h2>{teacher ? "Bring your classroom knowledge to life." : "Your learning starts with your classroom."}</h2><p>{teacher ? "Create a classroom, add a course and upload materials. Or prepare the guided demo to explore the full workflow." : "Join your teacher's classroom to access source-grounded tutoring, adaptive practice and your mastery map."}</p><button onClick={() => setPage(teacher ? "Classes" : "My Courses")}>{teacher ? "Open Classes" : "Join a classroom"}</button><button className="secondary" onClick={() => setPage("Demo Mode")}>Explore Demo Mode</button></section>}
      {page === "Dashboard" && course && (teacher ? <TeacherInsights key={`teacher-dashboard-${course.id}`} dashboard course={course} revision={revision} onSource={onSource} /> : <StudentDashboard course={course} revision={revision} onNavigate={setPage} />)}
      {noCoursePages.includes(page) && !course && <section className="classroomBox"><h2>Choose a course to continue</h2><p>{teacher ? "Create a course below or from Course Materials." : "Join a classroom and ask your teacher to add a course."}</p></section>}
      {page === "Ask LabTwin" && course && <AskLabTwin key={course.id} course={course} material={lecture} onSource={onSource} onClearLecture={() => setLecture(null)} />}
      {teacher && ["Classes", "Course Materials"].includes(page) && <CourseSetup key={`${page}-${revision}`} courses={courses} onRefresh={refresh} onSelect={setCourseId} />}
      {course && (page === "Course Materials" || (!teacher && page === "My Courses")) && <CourseMaterials key={course.id} course={course} teacher={teacher} onRefresh={refresh} onAsk={material => { setLecture(material); setPage("Ask LabTwin"); }} onSource={onSource} />}
      {!teacher && page === "Learning Path" && course && <LearningPath course={course} revision={revision} onSource={onSource} onPractice={onPractice} />}
      {!teacher && page === "Mastery Map" && course && <MasteryMap course={course} revision={revision} onSource={onSource} onPractice={onPractice} />}
      {!teacher && page === "Progress" && course && <ProgressReport course={course} revision={revision} onSource={onSource} onPractice={onPractice} />}
      {!teacher && page === "Viva" && course && <VivaWorkspace key={course.id} course={course} target={vivaTarget} onSource={onSource} onCompleted={changed} />}
      {teacher && page === "Assessments" && course && <AssessmentManager key={course.id} course={course} onSource={onSource} />}
      {!teacher && page === "Assessments" && course && <AssessmentWorkspace key={course.id} course={course} onSource={onSource} onCompleted={changed} />}
      {teacher && page === "Evaluation" && course && <EvaluationDashboard key={course.id} course={course} />}
      {teacher && page === "AI Insights" && course && <TeacherInsights key={course.id} course={course} revision={revision} onSource={onSource} />}
      {page === "Demo Mode" && <DemoPanel teacher={teacher} onSource={onSource} onPreview={preview} onReturnTeacher={teacherSession.current ? returnTeacher : null} refresh={changed} />}
      {!teacher && <section hidden={page !== "Practice"}><div className="practiceTabs"><button aria-pressed={practiceMode === "adaptive"} onClick={() => setPracticeMode("adaptive")}>Adaptive practice</button><button aria-pressed={practiceMode === "lab"} onClick={() => setPracticeMode("lab")}>Programming lab · existing workflow</button></div><div hidden={practiceMode !== "adaptive"}>{course ? <PracticeWorkspace key={course.id} course={course} initialTopic={practiceTopic} onSource={onSource} onCompleted={changed} onViva={onViva} /> : <p>Select a course for adaptive practice. The programming lab is ready in the next tab.</p>}</div><div hidden={practiceMode !== "lab"} className="legacyLab">{renderLab()}</div></section>}
      <div hidden={!classVisible}>{renderClassrooms({ mode: page, classroomId: course?.classroom_id, onSource, onViva, onChanged: changed })}</div>
    </main>
    <SourceViewer sourceId={sourceId} onAsk={source => { setLecture({ id: source.material_id, title: source.title, course_id: source.course_id, source_id: source.id }); setCourseId(source.course_id); setPage("Ask LabTwin"); setSourceId(null); }} onClose={() => { setSourceId(null); history.replaceState(null, "", location.pathname + location.search); }} />
  </div>;
}
