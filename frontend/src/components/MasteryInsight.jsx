import React, { useState } from "react";
import "./MasteryInsight.css";

function formatPercent(value) {

  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "0";
  }

  if (Number.isInteger(number)) {
    return number.toFixed(0);
  }

  return number.toFixed(1);
}


function clamp(value) {
  const number = Number(value);

  if (Number.isNaN(number)) {
    return 0;
  }

  return Math.max(0, Math.min(100, number));
}

function ProgressBar({ value }) {
  const score = clamp(value);

  return (
    <div className="mi-progress-track">
      <div
        className="mi-progress-fill"
        style={{ width: `${score}%` }}
      />
    </div>
  );
}

function ScoreRow({
  label,
  value,
  description = ""
}) {
  if (
    value === null ||
    value === undefined
  ) {
    return null;
  }

  const score = clamp(value);

  return (
    <div className="mi-score-row">

      <div className="mi-score-name">
        <span>{label}</span>

        {description && (
          <small>
            {description}
          </small>
        )}
      </div>

      <ProgressBar
        value={score}
      />

      <strong>
        {formatPercent(score)}%
      </strong>

    </div>
  );
}

function EvidenceItem({
  title,
  value,
  description
}) {
  return (
    <div className="mi-evidence-card">

      <span>
        {title}
      </span>

      <strong>
        {value}
      </strong>

      {description && (
        <small>
          {description}
        </small>
      )}

    </div>
  );
}

export default function MasteryInsight({
  topic = "Current Topic",
  mastery = 0,
  status = "Needs Verification",

  firstAttemptScore = 0,
  codeScore = 0,
  vivaScore = 0,

  verificationPassed = false,

  coreCorrectness = null,
  mechanism = null,
  application = null,
  coverage = null,

  hintLevel = 0,
  attempts = 0,

  misconception = "",
  recurringMisconception = false,

  labReadiness = 0
}) {

  const [showExplanation, setShowExplanation] =
    useState(false);

  const masteryValue =
    clamp(mastery);

  const firstValue =
    clamp(firstAttemptScore);

  const finalCodeValue =
    clamp(codeScore);

  const vivaValue =
    clamp(vivaScore);

  const readinessValue =
    clamp(labReadiness);

  const hint =
    Math.max(
      0,
      Math.min(
        3,
        Number(hintLevel) || 0
      )
    );

  /*
    This mirrors the Django mastery engine:

    Hint level 0 -> 100 independence
    Hint level 1 -> 70
    Hint level 2 -> 40
    Hint level 3 -> 10
  */
  const hintIndependence =
    Math.max(
      10,
      100 - (30 * hint)
    );

  const mastered =
    String(status)
      .trim()
      .toLowerCase() === "mastered";

  let evidenceConfidence = "LOW";

  if (
    verificationPassed &&
    Number(attempts) >= 2 &&
    masteryValue >= 80
  ) {
    evidenceConfidence = "HIGH";
  } else if (
    Number(attempts) >= 1 ||
    vivaValue > 0
  ) {
    evidenceConfidence = "MEDIUM";
  }

  const codeImprovement =
    Math.max(
      0,
      finalCodeValue - firstValue
    );

  const positives = [];
  const limits = [];

  if (finalCodeValue === 100) {
    positives.push(
      "The final program passed all hidden test cases."
    );
  } else if (finalCodeValue >= 80) {
    positives.push(
      "The final program passed most hidden-test requirements."
    );
  }

  if (vivaValue >= 90) {
    positives.push(
      "The viva demonstrated very strong conceptual understanding."
    );
  } else if (vivaValue >= 75) {
    positives.push(
      "The viva demonstrated sufficient conceptual understanding."
    );
  }

  if (verificationPassed) {
    positives.push(
      "Independent verification of this topic has been passed."
    );
  }

  if (hint === 0) {
    positives.push(
      "The solution was produced without hint assistance."
    );
  } else if (hint === 1) {
    positives.push(
      "Only low-level hint assistance was required."
    );
  }

  if (
    finalCodeValue >
    firstValue
  ) {
    positives.push(
      `Coding performance improved from ${formatPercent(firstValue)}% to ${formatPercent(finalCodeValue)}%.`
    );
  }

  if (
    firstValue > 0 &&
    firstValue < 80
  ) {
    limits.push(
      `The first attempt scored ${formatPercent(firstValue)}%, so first-attempt evidence is weaker.`
    );
  }

  if (
    vivaValue > 0 &&
    vivaValue < 75
  ) {
    limits.push(
      "Conceptual understanding still needs stronger viva evidence."
    );
  }

  if (hint >= 2) {
    limits.push(
      `Hint level ${hint} was required, reducing independence evidence.`
    );
  }

  if (!verificationPassed) {
    limits.push(
      "Independent verification has not yet been passed."
    );
  }

  if (recurringMisconception) {
    limits.push(
      "A topic-related misconception has appeared more than once."
    );
  }

  return (
    <section className="mastery-insight">

      <div className="mi-top">

        <div>

          <p className="mi-eyebrow">
            LABTWIN MASTERY ENGINE
          </p>

          <h2>
            {topic}
          </h2>

          <span
            className={
              mastered
                ? "mi-status mi-mastered"
                : "mi-status mi-verification"
            }
          >
            {status}
          </span>

        </div>


        <div className="mi-master-score">

          <strong>
            {formatPercent(masteryValue)}%
          </strong>

          <span>
            Topic Mastery
          </span>

        </div>

      </div>


      <ProgressBar
        value={masteryValue}
      />


      <div className="mi-evidence-grid">

        <EvidenceItem
          title="Evidence Confidence"
          value={evidenceConfidence}
          description="Based on attempts and verification"
        />

        <EvidenceItem
          title="Topic Attempts"
          value={attempts}
          description="Unique completed evidence"
        />

        <EvidenceItem
          title="Independent Verification"
          value={
            verificationPassed
              ? "PASSED"
              : "PENDING"
          }
        />

        <EvidenceItem
          title="Lab Readiness"
          value={`${Number(readinessValue).toFixed(1)}%`}
        />

      </div>


      <div className="mi-section">

        <div className="mi-section-heading">

          <div>
            <p className="mi-eyebrow">
              EVIDENCE
            </p>

            <h3>
              Programming Performance
            </h3>
          </div>

          {codeImprovement > 0 && (
            <span className="mi-gain">
              +{formatPercent(codeImprovement)}% code improvement
            </span>
          )}

        </div>


        <ScoreRow
          label="First Attempt"
          value={firstValue}
          description="Independent initial coding evidence"
        />

        <ScoreRow
          label="Final Code"
          value={finalCodeValue}
          description="Hidden-test performance of the submitted final code"
        />

      </div>


      <div className="mi-section">

        <p className="mi-eyebrow">
          CONCEPT EVIDENCE
        </p>

        <h3>
          Semantic Viva Assessment
        </h3>


        <ScoreRow
          label="Overall Understanding"
          value={vivaValue}
          description="Final semantic viva score"
        />


        <ScoreRow
          label="Core Correctness"
          value={coreCorrectness}
          description="Does the student understand what the concept is?"
        />


        <ScoreRow
          label="Mechanism"
          value={mechanism}
          description="Does the student understand how it works?"
        />


        <ScoreRow
          label="Application"
          value={application}
          description="Can the student connect it to practical use?"
        />


        <ScoreRow
          label="Question Coverage"
          value={coverage}
          description="How completely was the viva question answered?"
        />

      </div>


      <div className="mi-section">

        <p className="mi-eyebrow">
          INDEPENDENCE
        </p>

        <h3>
          Learning Behaviour
        </h3>


        <div className="mi-behaviour-grid">

          <div>

            <span>
              Highest Hint Level
            </span>

            <strong>
              {hint} / 3
            </strong>

          </div>


          <div>

            <span>
              Hint Independence
            </span>

            <strong>
              {formatPercent(hintIndependence)}%
            </strong>

          </div>


          <div>

            <span>
              Verification
            </span>

            <strong>
              {
                verificationPassed
                  ? "PASS"
                  : "PENDING"
              }
            </strong>

          </div>


          <div>

            <span>
              Recurring Misconception
            </span>

            <strong>
              {
                recurringMisconception
                  ? "YES"
                  : "NO"
              }
            </strong>

          </div>

        </div>

      </div>


      {misconception && (

        <div className="mi-section">

          <p className="mi-eyebrow">
            STUDENT MEMORY
          </p>

          <h3>
            Topic Misconception Evidence
          </h3>

          <div className="mi-misconception">
            {misconception}
          </div>

        </div>

      )}


      <div className="mi-section">

        <p className="mi-eyebrow">
          DETERMINISTIC ENGINE
        </p>

        <h3>
          How Topic Mastery Is Calculated
        </h3>


        <div className="mi-formula">

          <div>
            <strong>35%</strong>
            <span>First-attempt coding</span>
          </div>

          <div>
            <strong>25%</strong>
            <span>Concept understanding</span>
          </div>

          <div>
            <strong>15%</strong>
            <span>Final code</span>
          </div>

          <div>
            <strong>15%</strong>
            <span>Independent verification</span>
          </div>

          <div>
            <strong>10%</strong>
            <span>Hint independence</span>
          </div>

        </div>


        <p className="mi-formula-note">
          LabTwin uses recent unique evidence from the
          student's stored topic history. AI evaluates
          semantic understanding; Django calculates the
          numeric mastery result.
        </p>

      </div>


      <button
        type="button"
        className="mi-why-button"
        onClick={() =>
          setShowExplanation(
            (previous) => !previous
          )
        }
      >
        {
          showExplanation
            ? "Hide Mastery Explanation"
            : `Why ${formatPercent(masteryValue)}%?`
        }
      </button>


      {showExplanation && (

        <div className="mi-explanation">

          <h3>
            Evidence Behind This Decision
          </h3>


          {positives.length > 0 && (

            <div className="mi-positive">

              <h4>
                Evidence supporting mastery
              </h4>

              {positives.map(
                (item, index) => (

                  <p
                    key={
                      `positive-${index}`
                    }
                  >
                    + {item}
                  </p>

                )
              )}

            </div>

          )}


          {limits.length > 0 && (

            <div className="mi-limit">

              <h4>
                Evidence limiting mastery
              </h4>

              {limits.map(
                (item, index) => (

                  <p
                    key={
                      `limit-${index}`
                    }
                  >
                    - {item}
                  </p>

                )
              )}

            </div>

          )}

        </div>

      )}


      <div className="mi-section">

        <p className="mi-eyebrow">
          LEARNING JOURNEY
        </p>

        <h3>
          Current Topic Evidence
        </h3>


        <div className="mi-journey">

          <div>

            <strong>
              {formatPercent(firstValue)}%
            </strong>

            <span>
              First Code
            </span>

          </div>


          <span className="mi-arrow">
            →
          </span>


          <div>

            <strong>
              {formatPercent(finalCodeValue)}%
            </strong>

            <span>
              Final Code
            </span>

          </div>


          <span className="mi-arrow">
            →
          </span>


          <div>

            <strong>
              {formatPercent(vivaValue)}%
            </strong>

            <span>
              Viva
            </span>

          </div>


          <span className="mi-arrow">
            →
          </span>


          <div className="mi-final-step">

            <strong>
              {formatPercent(masteryValue)}%
            </strong>

            <span>
              Topic Mastery
            </span>

          </div>

        </div>

      </div>


      <div
        className={
          mastered
            ? "mi-decision mi-decision-mastered"
            : "mi-decision mi-decision-verification"
        }
      >

        <p className="mi-eyebrow">
          LABTWIN DECISION
        </p>


        <h3>
          {
            mastered
              ? "TOPIC MASTERED"
              : "MORE EVIDENCE REQUIRED"
          }
        </h3>


        {mastered ? (

          <>

            <p>
              LabTwin has enough coding,
              conceptual and verification evidence
              to mark this exact topic as mastered.
            </p>

            <p>
              <strong>
                Next action:
              </strong>{" "}
              move to another topic from the
              uploaded syllabus.
            </p>

          </>

        ) : (

          <>

            <p>
              LabTwin does not yet have enough
              independent evidence to confirm
              mastery.
            </p>

            <p>
              <strong>
                Next action:
              </strong>{" "}
              generate a different independent
              question on this same exact topic.
            </p>

          </>

        )}

      </div>

    </section>
  );
}
