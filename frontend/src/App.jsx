import { useEffect, useRef, useState } from "react";
import axios from "./api";
import ReactMarkdown from "react-markdown";
import "./App.css";
import LearningIntelligence from "./components/LearningIntelligence";
import ResponseHistory from "./components/ResponseHistory";
import ProgressiveHints from "./ProgressiveHints";
import MasteryInsight from "./components/MasteryInsight";

const API = (
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000/api"
).replace(/\/$/, "");


function App({ onLogout }) {
  const [historyVersion, setHistoryVersion] = useState(0);
  const refreshHistory = () => setHistoryVersion(value => value + 1);
  // RESTORE_ACTIVE_STUDENT_SESSION
  useEffect(() => {

    const savedStudent =
      sessionStorage.getItem(
        "labtwin_student"
      );

    if (!savedStudent) {
      return;
    }

    try {

      const parsedStudent =
        JSON.parse(
          savedStudent
        );

      setStudent(
        parsedStudent
      );


      axios
        .get(
          `${API}/progress/?student_id=${parsedStudent.student_id}`
        )
        .then(
          (response) => {

            setProgress(
              response.data
            );

          }
        )
        .catch(
          (error) => {

            console.error(
              "Could not restore dashboard:",
              error
            );

          }
        );


      axios
        .get(
          `${API}/student-session/?student_id=${parsedStudent.student_id}&activate=1`
        )
        .then(
          (response) => {

            const session =
              response.data
                ?.session;

            setSessionMeta(
              session || null
            );

            if (
              session
                ?.has_syllabus
            ) {

              setSyllabus({
                filename:
                  session.filename,

                language:
                  session.language,

                mode:
                  session.mode,

                topics:
                  session.topics || [],

                existing_question_count:
                  session.existing_question_count || 0,

                restored:
                  true,

                message:
                  "Previous syllabus restored."
              });

            }


            if (
              session
                ?.current_question
            ) {

              setQuestion(
                session
                  .current_question
              );

            }

          }
        )
        .catch(
          (error) => {

            console.error(
              "Could not restore learning session:",
              error
            );

          }
        );


    } catch {

      sessionStorage.removeItem(
        "labtwin_student"
      );

    }

  }, []);


  const [studentName, setStudentName] =
    useState("");

  const [student, setStudent] =
    useState(null);


  const [file, setFile] =
    useState(null);

  const [syllabus, setSyllabus] =
    useState(null);


  const [question, setQuestion] =
    useState(null);

  const [code, setCode] =
    useState("");


  const [analysis, setAnalysis] =
    useState(null);

  const [tutor, setTutor] =
    useState(null);


  const [correctedCode, setCorrectedCode] =
    useState("");

  const [vivaAnswer, setVivaAnswer] =
    useState("");


  const [evaluation, setEvaluation] =
    useState(null);

  const [progress, setProgress] =
    useState(null);


  const [loading, setLoading] =
    useState(false);

  // Prevent double-clicks / duplicate automatic requests
  // from launching two CrewAI question generators.
  const nextQuestionRequestRef =
    useRef(false);

  const [sessionMeta, setSessionMeta] =
    useState(null);

  const [activityMessage, setActivityMessage] =
    useState("");

  const [draftLoadedKey, setDraftLoadedKey] =
    useState("");

  const [hintLevelUsed, setHintLevelUsed] =
    useState(0);


  // ======================================================
  // RESTORE STUDENT
  // ======================================================


  // ======================================================
  // SESSION RESTORE
  // ======================================================

  const applySessionSnapshot = (
    session
  ) => {

    setSessionMeta(
      session || null
    );

    if (
      session
        ?.has_syllabus
    ) {

      setSyllabus({

        filename:
          session.filename,

        language:
          session.language,

        mode:
          session.mode,

        topics:
          session.topics || [],

        existing_question_count:
          session.existing_question_count || 0,

        restored:
          true,

        message:
          "Previous syllabus restored."

      });

    } else {

      setSyllabus(
        null
      );

    }


    if (
      session
        ?.current_question
    ) {

      setQuestion(
        session
          .current_question
      );

    } else {

      setQuestion(
        null
      );

    }

  };


  // ======================================================
  // LOCAL DRAFT RESTORE
  // ======================================================

  useEffect(() => {

    if (
      !student?.student_id ||
      !question?.id
    ) {
      return;
    }

    const key =
      "labtwin_draft_" +
      student.student_id +
      "_" +
      question.id;

    try {

      const saved =
        sessionStorage.getItem(
          key
        );

      if (saved) {

        const parsed =
          JSON.parse(
            saved
          );

        setCode(
          parsed.code || ""
        );

        setCorrectedCode(
          parsed.correctedCode || ""
        );

        setVivaAnswer(
          parsed.vivaAnswer || ""
        );

      }

    } catch (error) {

      console.error(
        "Could not restore draft:",
        error
      );

    }

    setDraftLoadedKey(
      key
    );

  }, [
    student?.student_id,
    question?.id
  ]);


  // ======================================================
  // LOCAL DRAFT AUTO SAVE
  // ======================================================

  useEffect(() => {

    if (
      !student?.student_id ||
      !question?.id
    ) {
      return;
    }

    const key =
      "labtwin_draft_" +
      student.student_id +
      "_" +
      question.id;

    if (
      draftLoadedKey !==
      key
    ) {
      return;
    }

    try {

      sessionStorage.setItem(
        key,
        JSON.stringify({
          code,
          correctedCode,
          vivaAnswer
        })
      );

    } catch (error) {

      console.error(
        "Could not save draft:",
        error
      );

    }

  }, [
    student?.student_id,
    question?.id,
    code,
    correctedCode,
    vivaAnswer,
    draftLoadedKey
  ]);


  // ======================================================
  // START STUDENT
  // ======================================================

  const startStudent = async (mode = "new") => {

    if (!studentName.trim()) {

      alert(
        "Enter student name."
      );

      return;
    }


    try {

      setLoading(true);


      const response =
        await axios.post(

          `${API}/start-student/`,

          {
            name: studentName,
            mode
          }

        );


      setStudent(
        response.data
      );

      // A student must never inherit another student's
      // syllabus, question, code, analysis or evaluation.
      setFile(null);
      setSyllabus(null);
      setQuestion(null);
      setCode("");
      setAnalysis(null);
      setTutor(null);
      setCorrectedCode("");
      setVivaAnswer("");
      setEvaluation(null);
      setProgress(null);
      setSessionMeta(null);
      setActivityMessage("");


      sessionStorage.setItem(

        "labtwin_student",

        JSON.stringify(
          response.data
        )

      );


      await loadProgress(
        response.data.student_id
      );

      applySessionSnapshot(
        response.data.session
      );


    } catch (error) {

      console.error(
        error
      );

      alert(
          error?.response?.data?.error ||
          error?.response?.data?.message ||
          "Could not start student session."
        );

    } finally {

      setLoading(false);

    }
  };


  // ======================================================
  // LOAD DASHBOARD
  // ======================================================

  const loadProgress = async (
    studentId = null
  ) => {

    const id =
      studentId ||
      student?.student_id;


    if (!id) {
      return;
    }


    try {

      const response =
        await axios.get(

          `${API}/progress/?student_id=${id}`

        );


      setProgress(
        response.data
      );

      return response.data;


    } catch (error) {

      console.error(
        error
      );

    }
  };


  // ======================================================
  // RESET QUESTION
  // ======================================================

  const resetQuestionWork = () => {

    setCode("");

    setAnalysis(null);

    setTutor(null);

    setCorrectedCode("");

    setVivaAnswer("");

    setEvaluation(null);

    setHintLevelUsed(0);

  };


  // ======================================================
  // UPLOAD SYLLABUS
  // ======================================================

  const uploadSyllabus = async () => {

    if (!file) {

      alert(
        "Choose syllabus PDF or TXT."
      );

      return;
    }


    try {

      setLoading(true);

      setActivityMessage(
        "Analyzing your syllabus. If AI capacity is busy, LabTwin will wait and retry automatically."
      );


      const formData =
        new FormData();


      formData.append(
        "syllabus",
        file
      );

      formData.append(
        "student_id",
        student?.student_id || ""
      );


      const response =
        await axios.post(

          `${API}/upload-syllabus/`,

          formData

        );


      setSyllabus(
        response.data
      );

      setSessionMeta(
        (previous) => ({
          ...(previous || {}),
          has_syllabus: true,
          filename: response.data.filename,
          language: response.data.language,
          mode: response.data.mode,
          topics: response.data.topics || [],
          existing_question_count:
            response.data.existing_question_count || 0
        })
      );

      setActivityMessage(
        response.data.cached
          ? "Saved syllabus analysis reused. No new AI syllabus analysis was required."
          : "Syllabus analyzed successfully."
      );


      // UNSUPPORTED_SYLLABUS_UI_GUARD

      if (
        response.data
          ?.execution_supported
        === false
      ) {

        setQuestion(
          null
        );

        setActivityMessage(
          response.data
            ?.unsupported_reason
          ||
          "This syllabus requires a runtime that is not supported by the current automatic code runner."
        );

        return;
      }


      await nextQuestion();


    } catch (error) {

      console.error(
        error
      );


      alert(

        error.response?.data?.error ||

        "Syllabus upload failed."

      );


    } finally {

      setLoading(false);

    }
  };


  // ======================================================
  // NEXT QUESTION
  // ======================================================

  const nextQuestion = async () => {

    // Hard guard against duplicate question requests.
    if (
      nextQuestionRequestRef.current
    ) {

      console.log(
        "Next-question request ignored: one is already running."
      );

      return;
    }

    nextQuestionRequestRef.current =
      true;

    try {

      setLoading(true);

      resetQuestionWork();


      const response =
        await axios.post(

          `${API}/adaptive-next-question/`,

          {
            student_id: student?.student_id,

            required_topic:
              evaluation &&
              evaluation?.evaluation?.status !== "Mastered"
                ? question?.topic
                : null,
          }

        );


      if (
        response.data.finished
      ) {

        alert(
          response.data.message
        );

        return;
      }


      setQuestion(
        response.data
      );


    } catch (error) {

      console.error(
        error
      );


      alert(

        error.response?.data?.error ||

        "Could not generate question."

      );


    } finally {

      nextQuestionRequestRef.current =
        false;

      setLoading(false);

    }
  };


  // ======================================================
  // SAVE MEMORY
  // ======================================================

  const saveAttempt = async ({
    initialScore,
    finalScore = null,
    vivaScore = null,
    misconception = "",
    topicRelated = false,
    topicMisconception = "",
    status,
    topic = question?.topic || "General",
    hintLevel = 0,
    verification = question?.is_verification || false
  }) => {

    if (
      !student ||
      !question
    ) {

      return;
    }


    try {

      await axios.post(

        `${API}/save-attempt/`,

        {

          student_id:
            student.student_id,

          question:
            question.problem,

          concept_key:
            question.concept_key,

          topic:
            topic,

          hint_level:
            hintLevel,

          verification:
            verification,

          initial_score:
            initialScore,

          final_score:
            finalScore,

          viva_score:
            vivaScore,

          misconception:
            misconception,

          topic_related:
            topicRelated,

          topic_misconception:
            topicMisconception,

          status:
            status

        }

      );


      const latestProgress =
        await loadProgress(
          student.student_id
        );

      return latestProgress;


    } catch (error) {

      console.error(
        "Memory save failed:",
        error
      );

    }
  };


  // ======================================================
  // ANALYZE
  // ======================================================

  const analyzeCode = async () => {

    if (!code.trim()) {

      alert(
        "Enter your code."
      );

      return;
    }


    try {

      setLoading(true);

      setAnalysis(null);

      setTutor(null);

      setEvaluation(null);

      setHintLevelUsed(0);


      const response =
        await axios.post(

          `${API}/analyze/`,

          {

            question_id:
              question.id,

            student_id:
              student?.student_id,

            code:
              code

          }

        );


      setAnalysis(
        response.data
      );


      const diagnosis =
        response.data.diagnosis;


      // ----------------------------------
      // CORRECT ON FIRST TRY
      // ----------------------------------

      if (
        response.data.test_score === 100 &&
        response.data.concept_requirement_met !== false
      ) {

        const tutorResponse =
          await axios.post(

            `${API}/tutor/`,

            {
              question_id:
                question?.id,

              language:
                question?.language,

              topic:
                question?.topic,

              problem:
                question?.problem,

              concept_key:
                diagnosis.concept_key,

              misconception:
                "",

              passed_code:
                true
            }

          );


        setTutor({
          ...tutorResponse.data,
          concept_check: true
        });

        setCorrectedCode(
          code
        );

        return;
      }


      // ----------------------------------
      // WRONG ? TUTOR
      // ----------------------------------

      const tutorResponse =
        await axios.post(

          `${API}/tutor/`,

          {

            concept_key:
              diagnosis.concept_key,

            topic:
              question.topic,

            misconception:
              diagnosis.misconception,

            topic_related:
              diagnosis.topic_related || false,

            error_category:
              diagnosis.error_category || "other",

            passed_code:
              false

          }

        );


      setTutor(
        tutorResponse.data
      );

      setHintLevelUsed(1);


    } catch (error) {

      console.error(
        error
      );


      alert(

        error.response?.data?.error ||

        "Analysis failed."

      );


    } finally {

      refreshHistory();
      setLoading(false);

    }
  };


  // ======================================================
  // EVALUATE CORRECTION
  // ======================================================

  const evaluateCode = async () => {

    try {

      setLoading(true);


      const hintLevel =
        (analysis?.test_score === 100 &&
                analysis?.concept_requirement_met !== false)
          ? 0
          : hintLevelUsed;


      const response =
        await axios.post(

          `${API}/evaluate/`,

          {

            question_id:
              question.id,

            student_id:
              student?.student_id,

            concept_key:
              analysis.diagnosis
                .concept_key,

            misconception:
              analysis?.test_score === 100
                ? ""
                : (
                    analysis?.diagnosis
                      ?.misconception || ""
                  ),

            code:
              correctedCode,

            first_hint: analysis?.diagnosis?.hint || tutor?.hint || "",
            viva_answer:
              vivaAnswer,

            initial_score:
              analysis.test_score,

            hint_level:
              hintLevel,

            verification:
              question?.is_verification || false,

            viva_question:
              tutor?.viva_question || "",

            expected_concepts:
              tutor?.expected_concepts || []

          }

        );


      const latestProgress =
        await saveAttempt({

          initialScore:
            analysis.test_score,

          finalScore:
            response.data.retest_score,

          vivaScore:
            response.data.evaluation.score,

          misconception:
            analysis?.test_score === 100
              ? ""
              : (
                  analysis?.diagnosis
                    ?.misconception || ""
                ),

          topicRelated:
            analysis?.test_score === 100
              ? false
              : (
                  analysis?.diagnosis
                    ?.topic_related || false
                ),

          topicMisconception:
            analysis?.test_score === 100
              ? ""
              : (
                  analysis?.diagnosis
                    ?.topic_misconception || ""
                ),

          status:
            response.data.evaluation.status,

          topic:
            question.topic,

          hintLevel:
            hintLevel,

          verification:
            question?.is_verification || false

        });


      const topicProgress =
        latestProgress?.topics?.find(
          (item) =>
            item.topic === question.topic
        );


      const finalStatus =
        topicProgress?.status ??
        response.data.evaluation.status;

      const finalMastery =
        topicProgress?.mastery_score ??
        response.data.topic_evidence_score;

      const verificationPassed =
        topicProgress?.verification_passed ??
        response.data.verification_passed ??
        (
          question?.is_verification === true &&
          Number(response.data.retest_score ?? 0) >= 80 &&
          Number(response.data.evaluation?.score ?? 0) >= 75 &&
          Number(hintLevel ?? 0) <= 1
        );

      const finalTopicProgress =
        topicProgress
          ? {
              ...topicProgress,
              verification_passed:
                Boolean(verificationPassed),
              verification_required:
                finalStatus !== "Mastered"
            }
          : {
              topic:
                question?.topic || "General",
              mastery_score:
                Number(finalMastery ?? 0),
              status:
                finalStatus,
              verification_passed:
                Boolean(verificationPassed),
              verification_required:
                finalStatus !== "Mastered"
            };

      setEvaluation({

        ...response.data,

        lab_readiness:
          latestProgress?.lab_readiness ??
          response.data.lab_readiness,

        topic_mastery:
          finalMastery,

        verification_passed:
          Boolean(verificationPassed),

        verification_required:
          finalStatus !== "Mastered",

        topic_progress:
          finalTopicProgress,

        evaluation: {
          ...response.data.evaluation,

          status:
            finalStatus
        }

      });


    } catch (error) {

      console.error(
        error
      );


      alert(

        error.response?.data?.error ||

        "Evaluation failed."

      );


    } finally {

      refreshHistory();
      setLoading(false);

    }
  };


  // ======================================================
  // CHANGE STUDENT
  // ======================================================

  const mastered = false;


  // ======================================================
  // SCORE EXPLANATIONS
  // ======================================================

  const getRetestReason = () => {

    const score = Number(
      evaluation?.retest_score ?? 0
    );

    if (score === 100) {
      return "Your final code passed all hidden test cases.";
    }

    return `Your final code passed ${score}% of the hidden-test evaluation.`;
  };


  const getConceptReason = () => {

    const score = Number(
      evaluation?.evaluation?.score ?? 0
    );

    if (score >= 90) {
      return "Your viva answer showed clear and complete understanding of the concept.";
    }

    if (score >= 75) {
      return "Your viva answer was mostly correct, but some concept details were incomplete.";
    }

    if (score >= 50) {
      return "Your viva answer showed partial understanding, so more conceptual verification is needed.";
    }

    return "Your viva answer missed or contradicted important parts of the concept.";
  };


  const getTopicMasteryReason = () => {

    const mastery = Number(
      evaluation?.topic_mastery ?? 0
    );

    const status =
      evaluation?.evaluation?.status || "";

    const initial = Number(
      analysis?.test_score ?? 0
    );

    const retest = Number(
      evaluation?.retest_score ?? 0
    );

    const viva = Number(
      evaluation?.evaluation?.score ?? 0
    );

    if (
      mastery >= 80 &&
      status === "Mastered"
    ) {
      return (
        `Mastery combines first-attempt coding (${initial}%), ` +
        `final code (${retest}%), viva (${viva}%), hint independence, ` +
        "and independent verification. The verification requirement has been passed."
      );
    }

    if (
      mastery >= 79 &&
      status.includes("Verification")
    ) {
      return (
        `Your latest code (${retest}%) and viva (${viva}%) are strong, ` +
        "but independent verification is still required. " +
        "LabTwin keeps an unverified topic below 80% until you prove it again independently."
      );
    }

    return (
      `This score combines first-attempt coding (${initial}%), ` +
      `final code (${retest}%), viva (${viva}%), hints used, ` +
      "previous evidence, and verification status. Earlier mistakes or hint use can keep mastery lower."
    );
  };


  const getReadinessReason = () => {

    const masteryAverage = Number(
      progress?.topic_mastery_average ?? 0
    );

    const coverage = Number(
      progress?.syllabus_coverage ?? 0
    );

    const readiness = Number(
      progress?.lab_readiness ??
      (
        (0.60 * masteryAverage) +
        (0.40 * coverage)
      )
    );

    return (
      `Overall readiness uses 60% tested-topic mastery and ` +
      `40% syllabus coverage. Current readiness is ` +
      `${readiness.toFixed(1)}%. ` +
      `LabTwin calculates this using the underlying unrounded ` +
      `values; the percentages shown on screen are rounded for readability.`
    );
  };


  // ======================================================
  // UI
  // ======================================================

  return (

    <div className="app">


      <div
        className={
          `topWorkspace ${
            student
              ? "studentWorkspace"
              : "startWorkspace"
          }`
        }
      >

        <aside className="leftRail">

      <div className="header">

        <h1>
          LabTwin AI
        </h1>

        <p>
          Autonomous Programming Lab Coach
        </p>

      </div>


      {activityMessage && (

        <div
          className={`labTwinSystemNotice ${loading ? "busy" : ""}`}
        >

          {loading && (
            <span className="labTwinSpinner" />
          )}

          <span>
            {activityMessage}
          </span>

        </div>

      )}


      {/* ================================================= */}
      {/* STUDENT */}
      {/* ================================================= */}

      {!student ? (

        <div className="card">

          <h2>
            Start
          </h2>

          <p>
            Enter your name to start a new session
            or continue your previous LabTwin progress.
          </p>

          <input
            type="text"
            value={studentName}
            placeholder="Student name"
            onChange={(event) =>
              setStudentName(
                event.target.value
              )
            }
            onKeyDown={(event) => {

              if (
                event.key === "Enter" &&
                studentName.trim()
              ) {
                startStudent("new");
              }

            }}
          />

          <div
            style={{
              display: "flex",
              gap: "12px",
              flexWrap: "wrap",
              marginTop: "14px"
            }}
          >

            <button
              type="button"
              disabled={
                !studentName.trim()
              }
              onClick={() =>
                startStudent("new")
              }
            >
              Start
            </button>


          </div>

        </div>

      ) : (

        <div className="card">

          <h2>
            Welcome, {student.name}
          </h2>

          <button
            type="button"
            onClick={
              onLogout
            }
          >
            Sign out
          </button>

        </div>

      )}



        </aside>

        <main className="mainRail">

      {/* ================================================= */}
      {/* SYLLABUS */}
      {/* ================================================= */}

      {student && (

        <div className="card">


          <h2>
            Syllabus
          </h2>


          <p className="syllabusHelpText">
            LabTwin will use the current syllabus unless you choose a new one.
          </p>


          <input

            type="file"

            accept=".pdf,.txt"

            onChange={(e) =>
              setFile(
                e.target.files[0]
              )
            }

          />


          <button
            onClick={
              uploadSyllabus
            }
            disabled={
              loading ||
              !file
            }
          >

            {
              loading
                ? "Analyzing..."
                : "Upload / Replace Syllabus"
            }

          </button>


          {syllabus && (

            <div
              style={{
                marginTop: "20px"
              }}
            >

              <p>
                {
                  syllabus.filename
                }
              </p>


              <p>

                <strong>
                  Mode:
                </strong>{" "}

                {
                  syllabus.mode ===
                  "existing_questions"

                    ? "Existing questions detected"

                    : "Questions generated from syllabus topics"
                }

              </p>


              <p>

                <strong>
                  Topics:
                </strong>{" "}

                {
                  syllabus.topics?.join(
                    ", "
                  )
                }

              </p>


              {
                syllabus.mode ===
                "existing_questions"
                && (

                  <p>

                    Questions found:{" "}

                    {
                      syllabus.existing_question_count
                    }

                  </p>

                )
              }

            </div>

          )}


        </div>

      )}


      {/* ================================================= */}
      {/* QUESTION */}
      {/* ================================================= */}

      {question && (

        <div className="card">


          <div
            style={{
              display: "flex",
              justifyContent:
                "space-between",
              alignItems: "center",
              gap: "20px"
            }}
          >


            <div>

              <h2>

                Question {
                  question.question_number
                }

              </h2>


              <p>

                {
                  question.is_verification

                    ? "Independent verification of your current weak topic"

                    : question.source ===
                      "syllabus"

                      ? "From uploaded syllabus"

                      : "Generated from syllabus topic"
                }

              </p>

            </div>


            <button
              onClick={
                nextQuestion
              }
              disabled={
                loading
              }
            >

              Next Question

            </button>

          </div>


          <div className="questionMetaRow">
            <div className="questionMetaItem">
              <span className="questionMetaLabel">
                Programming Language:
              </span>
          
              <span className="questionMetaValue">
                {question.language}
              </span>
            </div>
          
            <div className="questionMetaItem">
              <span className="questionMetaLabel">
                Topic:
              </span>
          
              <span className="questionMetaValue">
                {question.topic}
              </span>
            </div>
          </div>


          {question.language === "C" && (

            <div className="adaptiveBox">

              <strong>
                C question detected
              </strong>

              <p>
                LabTwin detected a C programming concept.
                Your C code will be compiled using GCC and tested automatically.
              </p>

            </div>

          )}




          <h3>
            Programming Problem
          </h3>


          <div
            className="problemText markdownProblem"
          >
            <ReactMarkdown>
              {
                String(
                  question.problem || ""
                ).replace(
                  /\\n/g,
                  "\n"
                )
              }
            </ReactMarkdown>
          </div>


          <h3>
            Your Code
          </h3>


          <textarea

            value={
              code
            }

            onChange={(e) =>
              setCode(
                e.target.value
              )
            }

            placeholder={
              `Write your ${question?.language || "programming"} code here...`
            }

          />


          <button
            onClick={
              analyzeCode
            }
            disabled={
              loading ||
              !code.trim() ||
              question?.execution_supported === false
            }
          >

            {
              loading
                ? "Working..."
                : "Analyze Code"
            }

          </button>


        </div>

      )}


      {/* ================================================= */}
      {/* ANALYSIS */}
      {/* ================================================= */}

      {analysis && (

        <div className="card">


          <h2>
            Code Analysis
          </h2>


          <h3>

            Initial Test Score:{" "}

            {
              analysis.test_score
            }%

          </h3>


          <h3>
            Hidden Test Cases
          </h3>


          {
            analysis
              .test_results
              .map(
                (test) => (

                  <p
                    key={
                      test.test
                    }
                  >

                    Test {
                      test.test
                    }:{" "}

                    {
                      test.passed
                        ? "PASS"
                        : "FAIL"
                    }

                  </p>

                )
              )
          }



          <h3>
            Misconception
          </h3>


          <p>

            {
              analysis
                .diagnosis
                .misconception
              ||
              "No misconception detected"
            }

          </p>

          {analysis.diagnosis.has_misconception && (
            <>
              <h3>Error Classification</h3>
              <p>
                {analysis.diagnosis.error_category || "other"}
              </p>

              <h3>Evidence About This Topic</h3>
              <p>
                {analysis.diagnosis.topic_related
                  ? `Topic-related misconception: ${analysis.diagnosis.topic_misconception || analysis.diagnosis.misconception}`
                  : `This coding error is not evidence of a weakness in ${question?.topic}.`}
              </p>
            </>
          )}


          <h3>
            Explanation
          </h3>


          <p>

            {
              analysis
                .diagnosis
                .explanation
            }

          </p>


          
          {
            analysis?.diagnosis?.hint &&
            analysis.diagnosis.hint
              .trim()
              .toLowerCase() !==
                "no correction is needed."
            && (
              <>
                <h3>
                  Hint
                </h3>

                <p>
                  {
                    analysis
                      .diagnosis
                      .hint
                  }
                </p>
              </>
            )
          }


        </div>

      )}


      {/* ================================================= */}
      {/* MASTERED */}
      {/* ================================================= */}

      {mastered && (

        <div className="card report">


          <h2>
            Current Problem Mastered
          </h2>


          <p>
            All hidden tests passed.
          </p>


          <div className="reportGrid">


            <div>

              <span>
                Test Score
              </span>

              <strong>
                100%
              </strong>

            </div>


            <div>

              <span>
                Status
              </span>

              <strong>
                Mastered
              </strong>

            </div>


            <div>

              <span>
                Retest Required
              </span>

              <strong>
                No
              </strong>

            </div>


            <div>

              <span>
                Readiness
              </span>

              <strong>
                100%
              </strong>

            </div>


          </div>


          <br />


          <button
            onClick={
              nextQuestion
            }
            disabled={
              loading
            }
          >

            {loading ? "Generating..." : "Next Question"}

          </button>


        </div>

      )}


      {/* ================================================= */}
      {/* TUTOR */}
      {/* ================================================= */}

      {tutor && (

        <div className="card">


          <h2>
            {
              (analysis?.test_score === 100 &&
                analysis?.concept_requirement_met !== false)
                ? "Concept Verification"
                : "Adaptive Tutor"
            }
          </h2>


          {!(analysis?.test_score === 100 &&
                analysis?.concept_requirement_met !== false) && (

            <>

              <ProgressiveHints
                key={`${student?.student_id}:${question?.id}`}
                studentId={student?.student_id}
                onSaved={refreshHistory}
                problem={
                  question?.problem || ""
                }
                questionId={
                  question?.id || ""
                }
                language={
                  question?.language || ""
                }
                topic={
                  question?.topic || ""
                }
                conceptKey={
                  analysis?.diagnosis?.concept_key ||
                  question?.concept_key ||
                  "OTHER"
                }
                misconception={
                  analysis?.diagnosis?.misconception ||
                  ""
                }
                firstHint={
                  analysis?.diagnosis?.hint ||
                  tutor.hint
                }
                initialLevel={
                  1
                }
                onLevelChange={
                  setHintLevelUsed
                }
              />


              <h3>
                Practice Problem
              </h3>


              <p>
                {
                  tutor.practice_problem
                }
              </p>

            </>

          )}


          {(analysis?.test_score === 100 &&
                analysis?.concept_requirement_met !== false) && (

            <p>
              Your code passed independently. LabTwin is now checking whether you understand the exact concept before marking the topic as mastered.
            </p>

          )}


          <h3>
            Viva Question
          </h3>


          <p>
            {
              tutor.viva_question
            }
          </p>


          <h3>
            {
              (analysis?.test_score === 100 &&
                analysis?.concept_requirement_met !== false)
                ? "Your Verified Code"
                : "Correct Your Code"
            }
          </h3>


          <textarea

            value={
              correctedCode
            }

            onChange={(e) =>
              setCorrectedCode(
                e.target.value
              )
            }

            placeholder={
              `Enter ${question?.language || "programming"} code...`
            }

          />


          <h3>
            Your Viva Answer
          </h3>


          <textarea

            value={
              vivaAnswer
            }

            onChange={(e) =>
              setVivaAnswer(
                e.target.value
              )
            }

            placeholder={
              "Explain the concept in your own words..."
            }

          />


          <button

            onClick={
              evaluateCode
            }

            disabled={
              loading ||
              !correctedCode.trim() ||
              !vivaAnswer.trim()
            }

          >

            {
              (analysis?.test_score === 100 &&
                analysis?.concept_requirement_met !== false)
                ? "Verify Understanding"
                : "Evaluate Improvement"
            }

          </button>


        </div>

      )}


      {/* ================================================= */}
      {/* FINAL */}
      {/* ================================================= */}

      {evaluation && (

        <div className="card report">


          <h2>
            LabTwin Final Report
          </h2>

          {/* FINAL_REPORT_SIMPLE_SUMMARY */}

          <div
            style={{
              margin: "12px 0 20px",
              padding: "14px 16px",
              borderRadius: "12px",
              background: "rgba(0,0,0,0.035)"
            }}
          >

            <strong>
              {question?.topic || "Current Topic"}
            </strong>

            <p
              style={{
                marginTop: "5px"
              }}
            >
              {
                evaluation?.evaluation?.status === "Mastered"
                  ? "Topic mastered. You can move to another syllabus topic."
                  : "More evidence is needed before this topic is mastered."
              }
            </p>

            <p
              style={{
                marginTop: "5px",
                fontSize: "0.9em"
              }}
            >
              Independent Verification:{" "}
              <strong>
                {
                  evaluation
                    ?.topic_progress
                    ?.verification_passed
                    ? "PASSED"
                    : "PENDING"
                }
              </strong>
            </p>

          </div>


          <div className="reportGrid">


            <div>

              <span>
                Final Code Score
              </span>

              <strong>
                {
                  evaluation
                    .retest_score
                }%
              </strong>

            </div>


            <div>

              <span>
                Concept Understanding
              </span>

              <strong>
                {
                  evaluation
                    .evaluation
                    .score
                }%
              </strong>

            </div>


            <div>

              <span>
                Current Topic Mastery
              </span>

              <strong>
                {
                  evaluation
                    .topic_mastery
                }%
              </strong>

            </div>


            <div>

              <span>
                Overall Lab Readiness
              </span>

              <strong>
                {
                  evaluation
                    .lab_readiness
                }%
              </strong>

            </div>


          </div>


          
          <details
            className="adaptiveBox final-score-details"
            style={{
              marginTop: "20px",
              textAlign: "left"
            }}
          >

            <summary
              style={{
                cursor: "pointer",
                fontWeight: 700,
                padding: "4px 0"
              }}
            >
              Why these scores?
            </summary>



            <p>
              <strong>Final Code Score: </strong>
              {getRetestReason()}
            </p>

            <p>
              <strong>Concept Understanding: </strong>
              {getConceptReason()}
            </p>

            <p>
              <strong>Current Topic Mastery: </strong>
              {getTopicMasteryReason()}
            </p>

            <p>
              <strong>Overall Lab Readiness: </strong>
              {getReadinessReason()}
            </p>

          

          </details>

          
          <details
            className="final-evidence-details"
            style={{
              marginTop: "20px",
              textAlign: "left"
            }}
          >

            <summary
              style={{
                cursor: "pointer",
                fontWeight: 700,
                padding: "12px 0"
              }}
            >
              View Detailed Evidence
            </summary>

            <p
              style={{
                marginBottom: "12px",
                opacity: 0.8
              }}
            >
              View mastery calculations, viva dimensions,
              verification evidence, hint independence and
              the complete learning journey.
            </p>

<MasteryInsight

            topic={
              question?.topic ||
              "Current Topic"
            }

            mastery={
              Number(
                evaluation?.topic_mastery ??
                0
              )
            }

            status={
              evaluation?.evaluation?.status ||
              "Needs Verification"
            }

            firstAttemptScore={
              Number(
                analysis?.test_score ??
                0
              )
            }

            codeScore={
              Number(
                evaluation?.retest_score ??
                0
              )
            }

            vivaScore={
              Number(
                evaluation?.evaluation?.score ??
                0
              )
            }

            verificationPassed={
              Boolean(
                evaluation
                  ?.topic_progress
                  ?.verification_passed
              )
            }

            coreCorrectness={
              evaluation
                ?.evaluation
                ?.dimensions
                ?.core_correctness
                ?.rating != null

                ? Number(
                    evaluation
                      .evaluation
                      .dimensions
                      .core_correctness
                      .rating
                  ) * 25

                : null
            }

            mechanism={
              evaluation
                ?.evaluation
                ?.dimensions
                ?.mechanism
                ?.rating != null

                ? Number(
                    evaluation
                      .evaluation
                      .dimensions
                      .mechanism
                      .rating
                  ) * 25

                : null
            }

            application={
              evaluation
                ?.evaluation
                ?.dimensions
                ?.application
                ?.rating != null

                ? Number(
                    evaluation
                      .evaluation
                      .dimensions
                      .application
                      .rating
                  ) * 25

                : null
            }

            coverage={
              evaluation
                ?.evaluation
                ?.dimensions
                ?.question_coverage
                ?.rating != null

                ? Number(
                    evaluation
                      .evaluation
                      .dimensions
                      .question_coverage
                      .rating
                  ) * 25

                : null
            }

            hintLevel={
              Number(
                evaluation?.hint_level ??
                hintLevelUsed ??
                0
              )
            }

            attempts={
              Number(
                evaluation
                  ?.topic_progress
                  ?.attempts ??
                0
              )
            }

            misconception={
              evaluation
                ?.topic_progress
                ?.last_misconception ||

              analysis
                ?.diagnosis
                ?.topic_misconception ||

              ""
            }

            recurringMisconception={
              Number(
                evaluation
                  ?.topic_progress
                  ?.misconception_count ??
                0
              ) > 1
            }

            labReadiness={
              Number(
                evaluation?.lab_readiness ??
                progress?.lab_readiness ??
                0
              )
            }

          />

          </details>



          <h3>
            Evaluator Feedback
          </h3>


          <p>
            {
              evaluation
                .evaluation
                .reason
            }
          </p>


          {
            evaluation
              .evaluation
              .partial_concepts
              ?.length > 0
            && (

              <p>
                Partially demonstrated:{" "}
                {
                  evaluation
                    .evaluation
                    .partial_concepts
                    .join(", ")
                }
              </p>

            )
          }

          {
            evaluation
              .evaluation
              .missing_concepts
              ?.length > 0
            && (

              <p>
                Missing concepts:{" "}
                {
                  evaluation
                    .evaluation
                    .missing_concepts
                    .join(", ")
                }
              </p>

            )
          }


          {
            evaluation
              .evaluation
              .contradictions
              ?.length > 0
            && (

              <p>
                Conceptual contradiction:{" "}
                {
                  evaluation
                    .evaluation
                    .contradictions
                    .join(", ")
                }
              </p>

            )
          }


          {
            evaluation
              .evaluation
              .status !== "Mastered"
            && (

              <p>
                LabTwin will keep the next question focused on this exact topic until independent mastery is demonstrated.
              </p>

            )
          }


          <button
            onClick={
              nextQuestion
            }
            disabled={
              loading
            }
          >

            {loading ? "Generating..." : "Next Question"}

          </button>


        </div>

      )}



        </main>

      </div>

      {/* ================================================= */}
      {/* DASHBOARD + LEARNING DETAILS BELOW ACTIVE FLOW */}
      {/* ================================================= */}

{/* ================================================= */}
      {/* DASHBOARD */}
      {/* ================================================= */}

      {student && progress && (

        <div className="card report">


          <h2>
            Learning Dashboard
          </h2>


          <div className="reportGrid">


            <div>

              <span>
                Questions Attempted
              </span>

              <strong>
                {
                  progress.questions_attempted
                }
              </strong>

            </div>


            <div>

              <span>
                Topics Mastered
              </span>

              <strong>
                {
                  progress.mastered
                }
              </strong>

            </div>


            <div>

              <span>
                Syllabus Coverage
              </span>

              <strong>
                {
                  progress.syllabus_coverage
                }%
              </strong>

            </div>


            <div>

              <span>
                Overall Lab Readiness
              </span>

              <strong>
                {
                  progress.lab_readiness
                }%
              </strong>

            </div>


          </div>


          <p
            style={{
              marginTop: "18px"
            }}
          >
            Tested-topic mastery average:{" "}
            <strong>
              {
                progress.topic_mastery_average
              }%
            </strong>
          </p>


          {progress.weakest_topic && (

            <div
              className="adaptiveBox learningPriorityBox"
              style={{
                marginTop: "20px"
              }}
            >

              <div className="priorityHeader">

                <div>

                  <div className="priorityEyebrow">
                    CURRENT LEARNING PRIORITY
                  </div>

                  <h3 className="priorityTopic">
                    {
                      progress
                        .weakest_topic
                        .topic
                    }
                  </h3>

                </div>

                <div className="priorityMasteryCircle">

                  <strong>
                    {
                      progress
                        .weakest_topic
                        .mastery_score
                    }%
                  </strong>

                  <span>
                    Mastery
                  </span>

                </div>

              </div>


              <div className="priorityMetric">

                <div className="priorityMetricTop">

                  <div>

                    <strong>
                      Topic Mastery
                    </strong>

                    <span className="metricInfo">
                      How well you can understand and
                      solve this topic independently.
                    </span>

                  </div>


                  <strong className="metricValue">

                    {
                      progress
                        .weakest_topic
                        .mastery_score
                    }%

                    {" â€” "}

                    {
                      Number(
                        progress
                          .weakest_topic
                          .mastery_score
                      ) >= 80

                        ? "Mastered"

                        : Number(
                            progress
                              .weakest_topic
                              .mastery_score
                          ) >= 60

                          ? "Nearly Mastered"

                          : Number(
                              progress
                                .weakest_topic
                                .mastery_score
                            ) >= 40

                            ? "Developing"

                            : "Beginning"
                    }

                  </strong>

                </div>


                <div className="masteryScale">

                  <div
                    className="masteryScaleFill"
                    style={{
                      width:
                        `${Math.min(
                          100,
                          Math.max(
                            0,
                            Number(
                              progress
                                .weakest_topic
                                .mastery_score
                            ) || 0
                          )
                        )}%`
                    }}
                  />

                </div>


                <div className="scaleLabels">
                  <span>Beginning</span>
                  <span>Developing</span>
                  <span>Nearly Mastered</span>
                  <span>Mastered</span>
                </div>

              </div>


              <div className="priorityInfoGrid">


                <div className="priorityInfoCard">

                  <span className="priorityInfoLabel">
                    WHAT IS MISSING?
                  </span>

                  <strong>

                    {
                      progress
                        .weakest_topic
                        .status === "Mastered"

                        ? "Nothing â€” Mastery Confirmed"

                        : progress
                            .weakest_topic
                            .status === "Needs Coding Practice"

                          ? "Better Coding Accuracy Needed"

                          : progress
                              .weakest_topic
                              .status === "Needs Practice"

                            ? "Stronger Understanding Needed"

                            : progress
                                .weakest_topic
                                .status === "Needs Verification"

                              ? "Independent Proof Needed"

                              : "More Practice Needed"
                    }

                  </strong>


                  <p>

                    {
                      progress
                        .weakest_topic
                        .status === "Mastered"

                        ? "You have shown enough coding, concept and independent evidence for this topic."

                        : progress
                            .weakest_topic
                            .status === "Needs Coding Practice"

                          ? "Your latest coding performance needs improvement before LabTwin can confirm this topic."

                          : progress
                              .weakest_topic
                              .status === "Needs Practice"

                            ? "Your concept understanding needs to become stronger before mastery can be confirmed."

                            : progress
                                .weakest_topic
                                .status === "Needs Verification"

                              ? "Complete another strong question on this exact topic with little or no help."

                              : "Keep practising this topic to build stronger mastery evidence."
                    }

                  </p>


                  <small className="technicalStatus">

                    LabTwin status:{" "}

                    {
                      progress
                        .weakest_topic
                        .status
                    }

                  </small>

                </div>


                <div className="priorityInfoCard">

                  <span className="priorityInfoLabel">
                    HINT RELIANCE
                  </span>

                  <strong>

                    {
                      Number(
                        progress
                          .weakest_topic
                          .average_hint_level
                      ) <= 0.5

                        ? "Very Low"

                        : Number(
                            progress
                              .weakest_topic
                              .average_hint_level
                          ) <= 1

                          ? "Low"

                          : Number(
                              progress
                                .weakest_topic
                                .average_hint_level
                            ) <= 2

                            ? "Moderate"

                            : "High"
                    }

                  </strong>


                  <p>

                    Average hint level:{" "}

                    <strong>
                      {
                        progress
                          .weakest_topic
                          .average_hint_level
                      } / 3
                    </strong>

                  </p>

                  <small>
                    Lower is better. 0 means no hints;
                    3 means maximum hint help.
                  </small>

                </div>

              </div>


              {
                progress
                  .weakest_topic
                  .verification_required
                && (

                  <div className="nextActionBox">

                    <strong>
                      What should I do next?
                    </strong>

                    <p>
                      Solve another different question
                      on this exact topic with as little
                      help as possible.
                    </p>

                  </div>

                )
              }


              {
                progress
                  .weakest_topic
                  .last_misconception
                && (

                  <div className="weaknessBox">

                    <strong>
                      What LabTwin noticed
                    </strong>

                    <p>
                      {
                        progress
                          .weakest_topic
                          .last_misconception
                      }
                    </p>

                  </div>

                )
              }


              <details className="scoreExplanation">

                <summary>
                  Why is my mastery {
                    progress
                      .weakest_topic
                      .mastery_score
                  }%?
                </summary>


                <div className="scoreExplanationBody">

                  <p>
                    Topic Mastery is not just your final
                    code score. LabTwin combines several
                    kinds of evidence.
                  </p>


                  {
                    progress
                      .weakest_topic
                      .mastery_breakdown
                    && (

                      <div className="actualEvidencePanel">

                        <div className="actualEvidenceHeader">

                          <div>

                            <span className="actualEvidenceEyebrow">
                              YOUR ACTUAL MASTERY EVIDENCE
                            </span>

                            <h4>
                              Where your {
                                progress
                                  .weakest_topic
                                  .mastery_score
                              }% came from
                            </h4>

                          </div>

                          <span className="evidenceAttempts">

                            Based on {
                              progress
                                .weakest_topic
                                .mastery_breakdown
                                .evidence_attempts
                            } recent {
                              progress
                                .weakest_topic
                                .mastery_breakdown
                                .evidence_attempts === 1
                                ? "attempt"
                                : "attempts"
                            }

                          </span>

                        </div>


                        <div className="actualEvidenceRow">

                          <div>

                            <strong>
                              First-attempt coding
                            </strong>

                            <small>
                              Your average: {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .scores
                                  .initial
                              }%
                            </small>

                          </div>

                          <div className="contributionScore">

                            <strong>
                              {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .contributions
                                  .initial
                              }
                            </strong>

                            <span>
                              / 35
                            </span>

                          </div>

                        </div>


                        <div className="actualEvidenceRow">

                          <div>

                            <strong>
                              Concept understanding / viva
                            </strong>

                            <small>
                              Your average: {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .scores
                                  .viva
                              }%
                            </small>

                          </div>

                          <div className="contributionScore">

                            <strong>
                              {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .contributions
                                  .viva
                              }
                            </strong>

                            <span>
                              / 25
                            </span>

                          </div>

                        </div>


                        <div className="actualEvidenceRow">

                          <div>

                            <strong>
                              Final corrected code
                            </strong>

                            <small>
                              Your average: {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .scores
                                  .final
                              }%
                            </small>

                          </div>

                          <div className="contributionScore">

                            <strong>
                              {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .contributions
                                  .final
                              }
                            </strong>

                            <span>
                              / 15
                            </span>

                          </div>

                        </div>


                        <div className="actualEvidenceRow">

                          <div>

                            <strong>
                              Independent verification
                            </strong>

                            <small>

                              {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .verification_passed

                                  ? "Passed"

                                  : "Not passed yet"
                              }

                            </small>

                          </div>

                          <div className="contributionScore">

                            <strong>
                              {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .contributions
                                  .verification
                              }
                            </strong>

                            <span>
                              / 15
                            </span>

                          </div>

                        </div>


                        <div className="actualEvidenceRow">

                          <div>

                            <strong>
                              Hint independence
                            </strong>

                            <small>
                              Independence score: {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .scores
                                  .hint_independence
                              }%
                            </small>

                          </div>

                          <div className="contributionScore">

                            <strong>
                              {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .contributions
                                  .hint_independence
                              }
                            </strong>

                            <span>
                              / 10
                            </span>

                          </div>

                        </div>


                        <div className="masteryMathBox">

                          <div>

                            <span>
                              Raw weighted total
                            </span>

                            <strong>
                              {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .raw_mastery
                              }%
                            </strong>

                          </div>

                          <div className="finalMasteryMath">

                            <span>
                              Final Topic Mastery
                            </span>

                            <strong>
                              {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .final_mastery
                              }%
                            </strong>

                          </div>

                        </div>


                        {
                          progress
                            .weakest_topic
                            .mastery_breakdown
                            .cap_reasons
                            ?.length > 0
                          && (

                            <div className="masteryCapBox">

                              <strong>
                                Mastery safeguards
                              </strong>

                              {
                                progress
                                  .weakest_topic
                                  .mastery_breakdown
                                  .cap_reasons
                                  .map(
                                    (
                                      reason,
                                      index
                                    ) => (

                                      <p
                                        key={
                                          `cap-${index}`
                                        }
                                      >
                                        {reason}
                                      </p>

                                    )
                                  )
                              }

                            </div>

                          )
                        }


                        <div className="mainLimiterBox">

                          <span>
                            MAIN THING LIMITING YOUR MASTERY
                          </span>

                          <strong>
                            {
                              progress
                                .weakest_topic
                                .mastery_breakdown
                                .main_limiter
                            }
                          </strong>

                        </div>

                      </div>

                    )
                  }



                  <div className="formulaRow">
                    <span>
                      First-attempt coding
                    </span>

                    <strong>
                      35%
                    </strong>
                  </div>


                  <div className="formulaRow">
                    <span>
                      Concept understanding / viva
                    </span>

                    <strong>
                      25%
                    </strong>
                  </div>


                  <div className="formulaRow">
                    <span>
                      Final corrected code
                    </span>

                    <strong>
                      15%
                    </strong>
                  </div>


                  <div className="formulaRow">
                    <span>
                      Independent verification
                    </span>

                    <strong>
                      15%
                    </strong>
                  </div>


                  <div className="formulaRow">
                    <span>
                      Hint independence
                    </span>

                    <strong>
                      10%
                    </strong>
                  </div>


                  <div className="explanationNote">

                    <strong>
                      Why does LabTwin do this?
                    </strong>

                    <p>
                      A program working after help does
                      not always mean the topic is fully
                      understood. LabTwin also checks
                      whether you understand the concept
                      and can reproduce it independently.
                    </p>

                  </div>

                </div>

              </details>


              <details className="scoreExplanation secondaryExplanation">

                <summary>
                  What does Hint Reliance mean?
                </summary>

                <div className="scoreExplanationBody">

                  <div className="hintScaleRow">
                    <strong>0</strong>
                    <span>
                      No hints needed
                    </span>
                  </div>

                  <div className="hintScaleRow">
                    <strong>1</strong>
                    <span>
                      Small hint
                    </span>
                  </div>

                  <div className="hintScaleRow">
                    <strong>2</strong>
                    <span>
                      More guidance
                    </span>
                  </div>

                  <div className="hintScaleRow">
                    <strong>3</strong>
                    <span>
                      Maximum hint assistance
                    </span>
                  </div>

                  <p className="hintMeaning">
                    So a hint reliance of {
                      progress
                        .weakest_topic
                        .average_hint_level
                    } / 3 means you usually require {

                      Number(
                        progress
                          .weakest_topic
                          .average_hint_level
                      ) <= 0.5

                        ? "almost no help."

                        : Number(
                            progress
                              .weakest_topic
                              .average_hint_level
                          ) <= 1

                          ? "only a little help."

                          : Number(
                              progress
                                .weakest_topic
                                .average_hint_level
                            ) <= 2

                            ? "some guidance."

                            : "significant help."
                    }
                  </p>

                </div>

              </details>

            </div>

          )}


        </div>

      )}


      {student && (
        <ResponseHistory key={student.student_id} api={API}
          studentId={student.student_id} version={historyVersion} />
      )}

      {student && progress && (

        <LearningIntelligence
          progress={
            progress
          }
          session={
            sessionMeta
          }
          question={
            question
          }
          onContinue={
            nextQuestion
          }
        />

      )}




    </div>

  );
}


export default App;













