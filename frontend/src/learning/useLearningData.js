import { useEffect, useState } from "react";
import { get, errorText } from "./api";

export default function useLearningData(course, endpoint, revision = 0, studentId) {
  const [data, setData] = useState(null), [error, setError] = useState("");
  const courseId = course?.id;
  useEffect(() => {
    let active = true; setData(null); setError("");
    if (courseId) get(`courses/${courseId}/${endpoint}/`, studentId ? { params: { student_id: studentId } } : undefined).then(result => { if (active) setData(result); }).catch(err => { if (active) setError(errorText(err)); });
    return () => { active = false; };
  }, [courseId, endpoint, revision, studentId]);
  return { data, error };
}
