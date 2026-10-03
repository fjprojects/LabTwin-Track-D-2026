import React, {
  useEffect,
  useState
} from "react";

import "./LearningIntelligence.css";


function clamp(value) {

  const number =
    Number(value);

  if (
    Number.isNaN(number)
  ) {
    return 0;
  }

  return Math.max(
    0,
    Math.min(
      100,
      number
    )
  );
}


function masteryLabel(value) {

  const score =
    clamp(value);

  if (score >= 80) {
    return "Mastered";
  }

  if (score >= 60) {
    return "Nearly Mastered";
  }

  if (score >= 40) {
    return "Developing";
  }

  return "Beginning";
}


function friendlyStatus(status) {

  switch (status) {

    case "Mastered":
      return "Mastery Confirmed";

    case "Needs Coding Practice":
      return "Improve Coding Accuracy";

    case "Needs Practice":
      return "Strengthen Understanding";

    case "Needs Verification":
      return "Independent Proof Needed";

    case "Developing":
      return "Keep Building Evidence";

    default:
      return status || "Learning";

  }
}


function hintLabel(value) {

  const number =
    Number(value) || 0;

  if (number <= 0.5) {
    return "Very Low";
  }

  if (number <= 1) {
    return "Low";
  }

  if (number <= 2) {
    return "Moderate";
  }

  return "High";
}


function MiniStat({
  label,
  value
}) {

  return (

    <div className="liMiniStat">

      <span>
        {label}
      </span>

      <strong>
        {value}
      </strong>

    </div>

  );
}


function MetricCard({
  title,
  value,
  explanation
}) {

  return (

    <div className="liMetricCard">

      <span className="liMetricTitle">
        {title}
      </span>

      <strong className="liMetricValue">
        {value}
      </strong>

      <p>
        {explanation}
      </p>

    </div>

  );
}


function TopicCard({
  topic
}) {

  const mastery =
    clamp(
      topic?.mastery_score
    );

  const attempts =
    Number(
      topic?.attempts || 0
    );

  const hint =
    Number(
      topic?.average_hint_level || 0
    );

  const verificationPassed =
    Boolean(
      topic?.verification_passed
    );


  return (

    <div className="liTopicCard">

      <div className="liTopicHeader">

        <div>

          <span className="liSmallLabel">
            SYLLABUS TOPIC
          </span>

          <h4>
            {
              topic?.topic ||
              "Topic"
            }
          </h4>

        </div>


        <div className="liTopicScore">

          <strong>
            {
              mastery.toFixed(1)
            }%
          </strong>

          <span>
            {
              masteryLabel(
                mastery
              )
            }
          </span>

        </div>

      </div>


      <div className="liProgressTrack">

        <div
          className="liProgressFill"
          style={{
            width:
              `${mastery}%`
          }}
        />

      </div>


      <div className="liTopicStats">

        <div>

          <span>
            Requirement
          </span>

          <strong>
            {
              friendlyStatus(
                topic?.status
              )
            }
          </strong>

        </div>


        <div>

          <span>
            Attempts
          </span>

          <strong>
            {attempts}
          </strong>

        </div>


        <div>

          <span>
            Hint Reliance
          </span>

          <strong>
            {
              hintLabel(
                hint
              )
            }
          </strong>

        </div>


        <div>

          <span>
            Verification
          </span>

          <strong>

            {
              verificationPassed
                ? "Passed"
                : "Pending"
            }

          </strong>

        </div>

      </div>


      {
        topic?.last_misconception
        && (

          <div className="liTopicNotice">

            <strong>
              LabTwin noticed:
            </strong>

            <span>
              {
                topic
                  .last_misconception
              }
            </span>

          </div>

        )
      }

    </div>

  );
}


function AttemptCard({
  attempt,
  index
}) {

  const initial =
    clamp(
      attempt?.initial_score
    );

  const finalScore =
    attempt?.final_score == null
      ? null
      : clamp(
          attempt.final_score
        );

  const viva =
    attempt?.viva_score == null
      ? null
      : clamp(
          attempt.viva_score
        );

  const mastery =
    attempt?.mastery_score == null
      ? null
      : clamp(
          attempt.mastery_score
        );


  return (

    <div className="liAttemptCard">

      <div className="liAttemptTop">

        <div>

          <span className="liSmallLabel">
            ATTEMPT {index + 1}
          </span>

          <strong>
            {
              attempt?.topic ||
              "Programming Topic"
            }
          </strong>

        </div>


        <span className="liAttemptStatus">

          {
            friendlyStatus(
              attempt?.status
            )
          }

        </span>

      </div>


      <div className="liAttemptScores">

        <div>

          <span>
            First Code
          </span>

          <strong>
            {
              initial.toFixed(0)
            }%
          </strong>

        </div>


        <div>

          <span>
            Final Code
          </span>

          <strong>

            {
              finalScore == null
                ? "â€”"
                : `${finalScore.toFixed(0)}%`
            }

          </strong>

        </div>


        <div>

          <span>
            Viva
          </span>

          <strong>

            {
              viva == null
                ? "â€”"
                : `${viva.toFixed(0)}%`
            }

          </strong>

        </div>


        <div>

          <span>
            Mastery
          </span>

          <strong>

            {
              mastery == null
                ? "â€”"
                : `${mastery.toFixed(1)}%`
            }

          </strong>

        </div>

      </div>


      {
        Number(
          attempt?.hint_level || 0
        ) > 0
        && (

          <p className="liAttemptHint">

            Highest hint level used:{" "}

            <strong>
              {
                attempt
                  .hint_level
              } / 3
            </strong>

          </p>

        )
      }

    </div>

  );
}


export default function LearningIntelligence({
  progress,
  session,
  question,
  onContinue
}) {

  const [
    viewMode,
    setViewMode
  ] = useState(() => {

    return (
      localStorage.getItem(
        "labtwin_dashboard_view"
      )
      ||
      "simple"
    );

  });


  useEffect(() => {

    localStorage.setItem(
      "labtwin_dashboard_view",
      viewMode
    );

  }, [
    viewMode
  ]);


  if (!progress) {
    return null;
  }


  const topics =
    Array.isArray(
      progress?.topics
    )
      ? progress.topics
      : [];


  const recentAttempts =
    Array.isArray(
      progress?.recent_attempts
    )
      ? [
          ...progress
            .recent_attempts
        ].reverse()
      : [];


  const questionsAttempted =
    Number(
      progress
        ?.questions_attempted || 0
    );


  const mastered =
    Number(
      progress
        ?.mastered || 0
    );


  const coverage =
    clamp(
      progress
        ?.syllabus_coverage
    );


  const readiness =
    clamp(
      progress
        ?.lab_readiness
    );


  const testedMastery =
    clamp(
      progress
        ?.topic_mastery_average
    );


  const verifiedTopics =
    topics.filter(
      (item) =>
        item
          ?.verification_passed
    ).length;


  const isNewStudent =
    questionsAttempted === 0 &&
    topics.length === 0;


  const detailed =
    viewMode === "detailed";


  return (

    <section className="learningIntelligence">


      {/* ================================================= */}
      {/* VIEW MODE */}
      {/* ================================================= */}

      <div className="liViewHeader">

        <div>

          <span className="liEyebrow">
            LEARNING DETAILS
          </span>

          <h2 style={{ color: "#0f172a" }}>Learning Insights</h2>

          <p>

            {
              detailed

                ? "Detailed evidence, topic progress and learning history are visible."

                : "Optional learning details are hidden to keep your dashboard simple."
            }

          </p>

        </div>


        <div className="liViewToggle">

          <button
            type="button"
            className={
              !detailed
                ? "active"
                : ""
            }
            onClick={() =>
              setViewMode(
                "simple"
              )
            }
          >
            Simple View
          </button>


          <button
            type="button"
            className={
              detailed
                ? "active"
                : ""
            }
            onClick={() =>
              setViewMode(
                "detailed"
              )
            }
          >
            Detailed View
          </button>

        </div>

      </div>


      {/* ================================================= */}
      {/* SIMPLE VIEW */}
      {/* ================================================= */}

      {!detailed && (

        <>

          <div className="liSimpleSummary">

            <MiniStat
              label="Tested Mastery"
              value={
                `${testedMastery.toFixed(1)}%`
              }
            />

            <MiniStat
              label="Coverage"
              value={
                `${coverage.toFixed(1)}%`
              }
            />

            <MiniStat
              label="Verified Topics"
              value={
                verifiedTopics
              }
            />

          </div>


          {
            session?.has_syllabus
            && (

              <div className="liCompactSession">

                <div>

                  <span className="liSmallLabel">
                    CURRENT SYLLABUS
                  </span>

                  <strong>
                    {
                      session?.filename ||
                      "Uploaded syllabus"
                    }
                  </strong>

                  <small>

                    {
                      session?.language ||
                      "Programming"
                    }

                    {" • "}

                    {
                      Array.isArray(
                        session?.topics
                      )
                        ? session.topics.length
                        : 0
                    }

                    {" topics"}

                  </small>

                </div>


                {
                  !question &&
                  onContinue
                  && (

                    <button
                      type="button"
                      onClick={
                        onContinue
                      }
                    >
                      Continue Learning
                    </button>

                  )
                }

              </div>

            )
          }


          <div className="liSimpleMessage">

            <strong>
              Want more information?
            </strong>

            <p>
              Switch to Detailed View to see
              readiness calculations, all topic
              scores, verification evidence and
              your learning history.
            </p>

          </div>

        </>

      )}


      {/* ================================================= */}
      {/* DETAILED VIEW */}
      {/* ================================================= */}

      {detailed && (

        <>


          {isNewStudent && (

            <div className="liEmptyState">

              <h3>
                Your learning profile is ready.
              </h3>

              <p>
                Upload your syllabus and complete
                your first question to begin
                collecting mastery evidence.
              </p>

            </div>

          )}


          <details className="liCollapsible">

            <summary>

              <div>

                <strong>
                  Detailed Learning Summary
                </strong>

                <span>
                  Scores and readiness calculation
                </span>

              </div>

            </summary>


            <div className="liCollapsibleBody">


              <div className="liMetricGrid">

                <MetricCard
                  title="Questions Attempted"
                  value={
                    questionsAttempted
                  }
                  explanation={
                    "Unique completed programming questions."
                  }
                />


                <MetricCard
                  title="Topics Mastered"
                  value={
                    mastered
                  }
                  explanation={
                    "Topics where sufficient evidence has been demonstrated."
                  }
                />


                <MetricCard
                  title="Syllabus Coverage"
                  value={
                    `${coverage.toFixed(1)}%`
                  }
                  explanation={
                    "How much of your syllabus has been tested."
                  }
                />


                <MetricCard
                  title="Overall Lab Readiness"
                  value={
                    `${readiness.toFixed(1)}%`
                  }
                  explanation={
                    "Overall preparation across mastery and coverage."
                  }
                />

              </div>


              <div className="liReadinessPanel">

                <span className="liSmallLabel">
                  READINESS BREAKDOWN
                </span>

                <h3>
                  {
                    readiness.toFixed(1)
                  }%
                </h3>


                <div className="liReadinessParts">

                  <div>

                    <span>
                      Tested-topic mastery
                    </span>

                    <strong>
                      {
                        testedMastery
                          .toFixed(1)
                      }%
                    </strong>

                    <small>
                      60% of readiness
                    </small>

                  </div>


                  <div>

                    <span>
                      Syllabus coverage
                    </span>

                    <strong>
                      {
                        coverage
                          .toFixed(1)
                      }%
                    </strong>

                    <small>
                      40% of readiness
                    </small>

                  </div>


                  <div>

                    <span>
                      Verified topics
                    </span>

                    <strong>
                      {
                        verifiedTopics
                      }
                    </strong>

                    <small>
                      Independent proof passed
                    </small>

                  </div>

                </div>


                <details className="liDetails">

                  <summary>
                    What does Lab Readiness mean?
                  </summary>

                  <div>

                    <p>
                      Lab Readiness measures your
                      preparation across the entire
                      syllabus.
                    </p>

                    <strong>
                      60% tested-topic mastery +
                      40% syllabus coverage.
                    </strong>

                  </div>

                </details>

              </div>

            </div>

          </details>


          {/* ============================================= */}
          {/* SAVED SESSION */}
          {/* ============================================= */}

          {
            session?.has_syllabus
            && (

              <details className="liCollapsible">

                <summary>

                  <div>

                    <strong>
                      Saved Learning Session
                    </strong>

                    <span>

                      {
                        session?.filename ||
                        "Uploaded syllabus"
                      }

                    </span>

                  </div>

                </summary>


                <div className="liCollapsibleBody">

                  <div className="liSessionPanel">

                    <span className="liSmallLabel">
                      CURRENT SYLLABUS
                    </span>

                    <h3>
                      {
                        session?.filename ||
                        "Uploaded syllabus"
                      }
                    </h3>


                    <div className="liSessionFacts">

                      <div>

                        <span>
                          Language
                        </span>

                        <strong>
                          {
                            session?.language ||
                            "â€”"
                          }
                        </strong>

                      </div>


                      <div>

                        <span>
                          Syllabus Topics
                        </span>

                        <strong>

                          {
                            Array.isArray(
                              session?.topics
                            )
                              ? session.topics.length
                              : 0
                          }

                        </strong>

                      </div>


                      <div>

                        <span>
                          Current Question
                        </span>

                        <strong>

                          {
                            session
                              ?.has_current_question

                              ? "Restored"

                              : "Not started"
                          }

                        </strong>

                      </div>

                    </div>


                    {
                      !question &&
                      onContinue
                      && (

                        <button
                          type="button"
                          className="liContinueButton"
                          onClick={
                            onContinue
                          }
                        >
                          Continue Learning
                        </button>

                      )
                    }

                  </div>

                </div>

              </details>

            )
          }


          {/* ============================================= */}
          {/* TOPICS */}
          {/* ============================================= */}

          {
            topics.length > 0
            && (

              <details className="liCollapsible">

                <summary>

                  <div>

                    <strong>
                      View All Topic Progress
                    </strong>

                    <span>

                      {
                        topics.length
                      }

                      {" tested "}

                      {
                        topics.length === 1
                          ? "topic"
                          : "topics"
                      }

                    </span>

                  </div>

                </summary>


                <div className="liCollapsibleBody">

                  <div className="liTopicGrid">

                    {
                      topics.map(
                        (
                          topic,
                          index
                        ) => (

                          <TopicCard
                            key={
                              `${topic?.topic}-${index}`
                            }
                            topic={
                              topic
                            }
                          />

                        )
                      )
                    }

                  </div>

                </div>

              </details>

            )
          }


          {/* ============================================= */}
          {/* HISTORY */}
          {/* ============================================= */}

          {
            recentAttempts.length > 0
            && (

              <details className="liCollapsible">

                <summary>

                  <div>

                    <strong>
                      View Learning History
                    </strong>

                    <span>
                      {
                        recentAttempts.length
                      } recent attempts
                    </span>

                  </div>

                </summary>


                <div className="liCollapsibleBody">

                  <div className="liAttemptList">

                    {
                      recentAttempts.map(
                        (
                          attempt,
                          index
                        ) => (

                          <AttemptCard
                            key={
                              `${attempt?.question}-${index}`
                            }
                            attempt={
                              attempt
                            }
                            index={
                              index
                            }
                          />

                        )
                      )
                    }

                  </div>

                </div>

              </details>

            )
          }


          {/* ============================================= */}
          {/* GUIDE */}
          {/* ============================================= */}

          <details className="liCollapsible">

            <summary>

              <div>

                <strong>
                  Dashboard Help
                </strong>

                <span>
                  Meaning of LabTwin metrics
                </span>

              </div>

            </summary>


            <div className="liCollapsibleBody">

              <div className="liGuideBody">

                <div>

                  <strong>
                    Topic Mastery
                  </strong>

                  <p>
                    Your understanding and ability
                    to independently solve one
                    exact syllabus topic.
                  </p>

                </div>


                <div>

                  <strong>
                    Hint Reliance
                  </strong>

                  <p>
                    How much assistance you usually
                    need. Lower is better.
                  </p>

                </div>


                <div>

                  <strong>
                    Verification
                  </strong>

                  <p>
                    Proof that you can solve a
                    different question independently.
                  </p>

                </div>


                <div>

                  <strong>
                    Syllabus Coverage
                  </strong>

                  <p>
                    How much of your syllabus has
                    actually been tested.
                  </p>

                </div>


                <div>

                  <strong>
                    Lab Readiness
                  </strong>

                  <p>
                    Your overall preparation across
                    both mastery and coverage.
                  </p>

                </div>


                <div>

                  <strong>
                    Learning History
                  </strong>

                  <p>
                    Your previous programming,
                    viva, hint and mastery evidence.
                  </p>

                </div>

              </div>

            </div>

          </details>

        </>

      )}

    </section>

  );
}

