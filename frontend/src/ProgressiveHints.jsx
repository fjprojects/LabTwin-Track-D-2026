import { useState } from "react";
import axios from "./api";



const API_BASE = (
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000/api"
).replace(/\/$/, "");

const API = API_BASE;

function ProgressiveHints({
  studentId,
  onSaved,
  problem,
  questionId,
  language,
  topic,
  conceptKey,
  misconception,
  firstHint,
  initialLevel = 1,
  onLevelChange
}) {

  const [level, setLevel] =
    useState(initialLevel);

  const [hint, setHint] = useState(
    firstHint || ""
  );

  const [loading, setLoading] =
    useState(false);


  const nextHint = async () => {

    if (level >= 3) {
      return;
    }


    try {

      setLoading(true);

      const nextLevel =
        level + 1;


      const response =
        await axios.post(

          `${API}/progressive-hint/`,

          {
            student_id: studentId,
            problem:
              problem,

            question_id:
              questionId,

            language:
              language,

            topic:
              topic,

            current_hint:
              hint,

            concept_key:
              conceptKey,

            misconception:
              misconception,

            level:
              nextLevel
          }

        );


      onSaved?.();
      setHint(
        response.data.hint
      );

      setLevel(
        nextLevel
      );

      if (onLevelChange) {
        onLevelChange(
          nextLevel
        );
      }


    } catch (error) {

      console.error(
        error
      );

      alert(
        "Could not generate another hint."
      );

    } finally {

      setLoading(false);

    }
  };


  return (

    <div>

      <h3>
        Progressive Hint
      </h3>


      <div className="adaptiveBox">

        <strong>
          Hint Level {level} of 3
        </strong>

        <p>
          {hint}
        </p>

      </div>


      {level < 3 && (

        <button
          onClick={
            nextHint
          }
          disabled={
            loading
          }
        >

          {
            loading
              ? "Generating Hint..."
              : `Need More Help - Hint ${level + 1}`
          }

        </button>

      )}


      {level === 3 && (

        <p
          style={{
            marginTop: "12px",
            fontWeight: "600"
          }}
        >
          Maximum hint level reached. Try correcting
          the program using the guidance above.
        </p>

      )}

    </div>

  );
}


export default ProgressiveHints;
