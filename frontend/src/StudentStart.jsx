import { useState } from "react";
import axios from "./api";



const API_BASE = (
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000/api"
).replace(/\/$/, "");

const API = API_BASE;

function StudentStart({
  onStudentStarted
}) {

  const [name, setName] =
    useState("");

  const [loading, setLoading] =
    useState(false);


  const start = async (mode) => {

    if (!name.trim()) {
      alert("Enter student name.");
      return;
    }

    try {

      setLoading(true);

      const response =
        await axios.post(

          `${API}/start-student/`,

          {
            name: name.trim(),
            mode: mode
          }

        );

      sessionStorage.setItem(
        "labtwin_student",
        JSON.stringify(
          response.data
        )
      );

      onStudentStarted(
        response.data
      );

    } catch (error) {

      console.error(error);

      alert(
        error.response?.data?.error ||
        "Could not start student session."
      );

    } finally {

      setLoading(false);

    }
  };


  return (

    <div className="card">

      <h2>
        Start Learning Session
      </h2>

      <p>
        Enter your name. Start a fresh session
        or continue previously saved progress.
      </p>

      <input
        type="text"
        value={name}
        onChange={(e) =>
          setName(e.target.value)
        }
        placeholder="Student name"
      />

      <div
        style={{
          display: "flex",
          gap: "10px",
          flexWrap: "wrap",
          marginTop: "10px"
        }}
      >

        <button
          onClick={() =>
            start("new")
          }
          disabled={loading}
        >
          Start New Session
        </button>


        <button
          onClick={() =>
            start("continue")
          }
          disabled={loading}
        >
          Continue Previous Progress
        </button>

      </div>

    </div>

  );
}

export default StudentStart;


