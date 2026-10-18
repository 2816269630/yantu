"""Create the first owner without exposing a public administrator signup route."""

import getpass
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ...core.models import Base, Member, Team, User
from ...core.security import hash_password


def main():
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./yantu.db")
    email = input("负责人邮箱：").strip().lower()
    name = input("显示名称：").strip()
    team_name = input("课题组名称：").strip()
    password = getpass.getpass("登录密码（至少 12 位）：")
    if "@" not in email or not name or not team_name or len(password) < 12:
        raise SystemExit("邮箱、名称或密码不符合要求")
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("此邮箱已存在；请直接登录")
        owner = User(email=email, display_name=name, password_hash=hash_password(password))
        team = Team(name=team_name)
        db.add_all((owner, team))
        db.flush()
        db.add(Member(team_id=team.id, user_id=owner.id, role="owner"))
        db.commit()
        print(f"已创建负责人和课题组，课题组 ID：{team.id}")


if __name__ == "__main__":
    main()
