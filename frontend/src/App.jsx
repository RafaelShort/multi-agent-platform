import Sidebar from "./components/Sidebar";
import Chat from "./components/Chat";

export default function App() {
  return (
    <div className="flex h-full">
      <Sidebar />
      <Chat />
    </div>
  );
}
