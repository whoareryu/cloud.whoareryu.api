from apps.titanic.app.walter_reader import WalterReader
from apps.titanic.app.rose_model import RoseModel as RoseModel

import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score


class JackService:
    def __init__(self):
        self.walter = WalterReader()
        self.rose = RoseModel()

    def get_data(self):
        return self.walter.get_data()

    def get_count(self):
        return self.walter.get_count()

    def get_count_survived(self):
        return self.walter.get_count_survived()

    def get_count_dead(self):
        return self.walter.get_count_dead()
    
    def has_decision_tree_model(self):
        return self.rose.has_decision_tree_model()


    def get_training_model_name(self) -> str:
        df = pd.read_csv(Path(__file__).resolve().parent / "Titanic-Dataset.csv")

        y = df["Survived"].astype(int)
        X = df[["Pclass", "Sex", "Age", "SibSp", "Parch", "Fare", "Embarked"]].copy()
        X["Age"] = X["Age"].fillna(X["Age"].median())
        X["Embarked"] = X["Embarked"].fillna(X["Embarked"].mode(dropna=True)[0])
        X = pd.get_dummies(X, columns=["Sex", "Embarked"], drop_first=True)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        model = self.rose.model
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)

        return f"{type(model).__name__} (accuracy={acc:.4f})"

