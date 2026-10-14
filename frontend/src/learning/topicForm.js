// Match the topic API's rules before sending a request; the server still
// checks ownership and duplicates against its current database state.
export function topicPayload(rawName, prerequisite, topics) {
  if (typeof rawName !== "string" || !rawName.trim() || rawName.trim().length > 200) {
    throw new Error("Enter a topic name of up to 200 characters.");
  }
  const name = rawName.trim();
  if (topics.some(topic => topic.name === name)) {
    throw new Error("A topic with this name already exists in this course. Use a different name.");
  }
  const prerequisites = [];
  if (prerequisite !== "") {
    const id = Number(prerequisite);
    if (!Number.isSafeInteger(id) || id <= 0 || !topics.some(topic => topic.id === id)) {
      throw new Error("Choose prerequisites from this course. Refresh the course if a topic is no longer available.");
    }
    prerequisites.push(id);
  }
  return { name, prerequisites };
}
