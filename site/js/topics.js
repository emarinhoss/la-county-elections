// The county lists 22 contest groups. People think in a handful of topics, so the site groups them. A group that is not named
// here (a different election may have new ones) lands in "Other" instead of disappearing.
export const TOPICS = [
  { id: "statewide", label: "Statewide offices", blurb: "Governor, attorney general and other state officers",
    groups: ["Governor", "Lieutenant Governor", "Secretary of State", "Controller", "Treasurer", "Attorney General", "Insurance Commissioner", "Board of Equalization", "Superintendent Public Inst"] },
  { id: "state-measures", label: "State measures", blurb: "Propositions on the statewide ballot", groups: ["State Measures"] },
  { id: "county", label: "County", blurb: "Sheriff and county ballot measures", groups: ["County Measures", "Sheriff"] },
  { id: "legislature", label: "Congress & legislature", blurb: "U.S. House, State Senate and Assembly seats", groups: ["U.S. Representative", "State Senator", "Member of the Assembly"] },
  { id: "judges", label: "Judges", blurb: "Superior Court seats and retention votes", groups: ["Supreme Court Justices", "Appellate Court Justices", "Judge Superior Court"] },
  { id: "local", label: "Schools & districts", blurb: "School boards, libraries, water and park districts", groups: ["Schools", "Library Districts", "Water Districts", "Recreation and Park"] },
  { id: "cities", label: "City contests", blurb: "Mayors, councils and local measures", cities: true },
];
export function topicOf(groupName) {
  return (TOPICS.find((t) => t.groups && t.groups.includes(groupName)) || { id: "other" }).id;
}
export const topicLabel = (id) => (TOPICS.find((t) => t.id === id) || { label: "Other" }).label;
