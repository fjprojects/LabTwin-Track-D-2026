// Match the topic API's rules before sending a request; the server still
// checks ownership and duplicates against its current database state.
export function topicPayload(rawName, prerequisite, topics) {
  if (typeof rawName !== "string" || !rawName.trim() || rawName.trim().length > 200) {
    throw new Error("Enter a topic name of up to 200 characters.");
  }
  const name = rawName.trim();
  const duplicate = duplicateTopicMessage(name, topics);
  if (duplicate) throw new Error(duplicate);
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

// Warn while typing using the same exact-name rule as the course API.
export function duplicateTopicMessage(rawName, topics) {
  const name = typeof rawName === "string" ? rawName.trim() : "";
  return name && topics.some(topic => topic.name === name)
    ? "A topic with this name already exists in this course. Use a different name."
    : "";
}
