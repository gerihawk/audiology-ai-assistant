import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <section>
      <h2>Página no encontrada</h2>
      <p>La URL solicitada no corresponde a ninguna sección de la aplicación.</p>
      <Link to="/patients">Volver a pacientes</Link>
    </section>
  )
}
